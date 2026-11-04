import base64
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

plugin_path = Path(sys.argv.pop(1))
spec = importlib.util.spec_from_file_location(
    "birthday_under_test",
    plugin_path / "main.py",
    submodule_search_locations=[str(plugin_path)],
)
birthday = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = birthday
spec.loader.exec_module(birthday)


class Client:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def call_action(self, action, **params):
        if self.fail:
            raise RuntimeError("Upload failed")
        self.calls.append((action, params))


class PortraitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.directory = self.data / "avatars/test/123"
        self.directory.mkdir(parents=True)
        (self.directory / "original.jpg").write_bytes(b"original-avatar")
        self.state = self.directory / "active.json"
        self.client = Client()
        self.rule = {
            "platform_id": "test",
            "group_id": 123,
            "avatar_enabled": True,
            "zone": ZoneInfo("Asia/Tokyo"),
            "birthdays": {"11-04": ["千石由乃"], "11-05": ["千石由乃"]},
        }
        self.renders = []

        async def render(original, output, names, day, settings=None):
            self.assertEqual(original.read_bytes(), b"original-avatar")
            self.renders.append((names, day))
            output.write_bytes(("frame:" + ",".join(names)).encode())

        patcher = patch.object(birthday, "render_portrait", render)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def sync(self, day="2026-11-04", hour=12):
        day = date.fromisoformat(day)
        now = datetime(day.year, day.month, day.day, hour, tzinfo=self.rule["zone"])
        await birthday.sync_group_portrait(self.client, self.rule, day, self.data, now)

    async def test_upgrade_replaces_today_once(self):
        self.state.write_text(json.dumps({"names": ["千石由乃"]}))
        await self.sync()
        await self.sync()
        self.assertEqual(len(self.client.calls), 1)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["event"], "2026-11-04")
        self.assertEqual(state["template"], birthday.FRAME_VERSION)

    async def test_same_name_on_next_day_and_next_year_updates(self):
        await self.sync()
        await self.sync("2026-11-05")
        await self.sync("2027-11-04")
        self.assertEqual(len(self.client.calls), 3)
        self.assertEqual(self.renders[-1][1], date(2027, 11, 4))

    async def test_multiple_birthdays_rotate_and_restart_is_idempotent(self):
        self.rule["birthdays"]["11-04"] = ["冰川纱夜", "冰川日菜", "伊藤彩沙"]
        for hour in range(3):
            await self.sync(hour=hour)
            await self.sync(hour=hour)
        self.assertEqual(
            [r[0] for r in self.renders], [["冰川纱夜"], ["冰川日菜"], ["伊藤彩沙"]]
        )
        self.assertEqual(len(self.client.calls), 3)

    async def test_no_birthday_restores_original_once(self):
        await self.sync()
        await self.sync("2026-11-06")
        await self.sync("2026-11-06")
        self.assertFalse(self.state.exists())
        payload = self.client.calls[-1][1]["file"].removeprefix("base64://")
        self.assertEqual(base64.b64decode(payload), b"original-avatar")
        self.assertEqual(len(self.client.calls), 2)

    async def test_upload_failure_keeps_state_for_next_attempt(self):
        self.state.write_text(json.dumps({"names": ["大和麻弥"]}))
        before = self.state.read_text()
        self.client.fail = True
        with self.assertRaises(RuntimeError):
            await self.sync()
        self.assertEqual(self.state.read_text(), before)
        self.client.fail = False
        await self.sync()
        self.assertEqual(json.loads(self.state.read_text())["names"], ["千石由乃"])

    async def test_disabled_avatar_restores_original(self):
        await self.sync()
        self.rule["avatar_enabled"] = False
        await self.sync()
        self.assertFalse(self.state.exists())

    async def test_unmapped_calendar_preserves_grouped_names(self):
        self.rule["birthdays"]["11-04"] = ["自定义甲", "自定义乙"]
        await self.sync()
        self.assertEqual(self.renders[0][0], ["自定义甲", "自定义乙"])

    def test_own_calendar_and_imports(self):
        rule = {"enabled": True, "group_id": "123", "platform_id": "test"}
        loaded = birthday.load_group_rules({"group_rules": [rule]}, self.data)[0]
        self.assertEqual(sum(map(len, loaded["birthdays"].values())), 119)
        self.assertEqual(str(loaded["zone"]), "Asia/Tokyo")
        (self.data / "custom.csv").write_text(
            "姓名,生日\n自定义,11-04\n", encoding="utf-8"
        )
        rule.update(use_builtin_calendar=False, import_names=["custom.csv"])
        loaded = birthday.load_group_rules(
            {"group_rules": [rule], "import_files": ["custom.csv"]}, self.data
        )[0]
        self.assertEqual(loaded["birthdays"], {"11-04": ["自定义"]})

    def test_calendar_color_and_actor_coverage(self):
        calendar = json.loads(
            (plugin_path / "birthdays.json").read_text(encoding="utf-8")
        )
        names = [n for items in calendar.values() for n in items]
        self.assertEqual(len(names), 119)
        for name in names:
            self.assertRegex(birthday.PORTRAIT_PEOPLE[name]["color"], r"^#[0-9A-F]{6}$")
        self.assertEqual(birthday.PORTRAIT_PEOPLE["反田叶月"]["color"], "#BBFF77")
        self.assertEqual(birthday.PORTRAIT_PEOPLE["黑泽朋世"]["color"], "#DD33CC")
        self.assertEqual(birthday.PORTRAIT_PEOPLE["鸣原令王那"]["name"], "鳰原令王那")


class CalendarBlackBoxTests(unittest.TestCase):
    def test_formats_and_deduplication(self):
        for value in ["11-04", "11/04", "2026.11.4", "11月4日", date(2026, 11, 4)]:
            with self.subTest(value=value):
                result = birthday.calendar_from_rows(
                    [["姓名", "生日"], ["甲", value], ["甲", value], ["乙", ""]],
                    "input",
                )
                self.assertEqual(result, ({"11-04": ["甲"]}, 1, True))

    def test_invalid_dates(self):
        for value in ["02-30", "13-01", "abc", "00-01"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                birthday.calendar_from_rows([["姓名", "生日"], ["甲", value]], "input")

    def test_title_row_month_columns_and_leap_day(self):
        result = birthday.calendar_from_rows(
            [
                ["标题"],
                ["角色名", "月份", "日期"],
                ["甲", "2月", "29日"],
                ["", "1", "1"],
            ],
            "input",
        )
        self.assertEqual(result, ({"02-29": ["甲"]}, 0, True))

    def test_group_names(self):
        calendar = {"11-04": ["甲", "乙"]}
        self.assertEqual(
            birthday.group_name_for_day("群@旧", date(2026, 11, 4), calendar),
            "群@甲&乙 生日快乐",
        )
        self.assertEqual(
            birthday.group_name_for_day("群@旧", date(2026, 11, 5), calendar), "群"
        )

    def test_file_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, content in [
                ("empty.csv", "姓名,生日"),
                ("bad.csv", "姓名,生日\n甲,abc"),
                ("bad.txt", ""),
            ]:
                file = root / filename
                file.write_text(content, encoding="utf-8")
                with self.subTest(file=filename), self.assertRaises(ValueError):
                    birthday.import_calendar(file)
            from openpyxl import Workbook

            book = Workbook()
            book.active.append(["姓名", "生日"])
            book.active.append(["甲", "11-04"])
            sheet = book.create_sheet()
            sheet.append(["姓名", "生日"])
            sheet.append(["乙", "02-29"])
            file = root / "data.xlsx"
            book.save(file)
            book.close()
            self.assertEqual(
                birthday.import_calendar(file), ({"11-04": ["甲"], "02-29": ["乙"]}, 0)
            )

    def test_rule_errors_and_disabled_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rule = {"enabled": True, "platform_id": "test", "group_id": "1"}
            for rules in [
                [rule, rule],
                [dict(rule, use_builtin_calendar=False)],
                [dict(rule, import_names=["missing.csv"])],
            ]:
                with self.subTest(rules=rules), self.assertRaises(ValueError):
                    birthday.load_group_rules({"group_rules": rules}, root)
            self.assertEqual(
                birthday.load_group_rules({"group_rules": [{"enabled": False}]}, root),
                [],
            )


class SchedulerWhiteBoxTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_group_does_not_block_other_group_or_mark_success(self):
        from unittest.mock import AsyncMock

        plugin = object.__new__(birthday.BanGDreamBirthdayPlugin)
        plugin.rules = [
            {
                "platform_id": "test",
                "group_id": i,
                "zone": ZoneInfo("Asia/Tokyo"),
                "birthdays": {},
            }
            for i in [1, 2]
        ]
        plugin.checked_days = {}
        plugin.sync_group_name = AsyncMock(side_effect=[RuntimeError("failure"), True])
        import asyncio

        with (
            patch.object(
                birthday.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await plugin.watch_birthdays()
        self.assertNotIn(("test", 1), plugin.checked_days)
        self.assertIn(("test", 2), plugin.checked_days)
        self.assertEqual(plugin.sync_group_name.await_count, 2)

    async def test_missing_platform_leaves_check_pending(self):
        from types import SimpleNamespace

        plugin = object.__new__(birthday.BanGDreamBirthdayPlugin)
        plugin.context = SimpleNamespace(
            platform_manager=SimpleNamespace(platform_insts=[])
        )
        self.assertFalse(
            await plugin.sync_group_name({"platform_id": "missing"}, date(2026, 11, 4))
        )

    async def test_terminate_cancels_task(self):
        import asyncio

        plugin = object.__new__(birthday.BanGDreamBirthdayPlugin)
        plugin.task = asyncio.create_task(asyncio.sleep(60))
        await plugin.terminate()
        self.assertTrue(plugin.task.cancelled())


class PresentationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)

    def test_default_uses_bundled_fonts_and_star(self):
        settings = birthday.load_settings({}, self.data)
        self.assertEqual(
            set(settings["assets"]), {"font_file", "cjk_font_file", "decoration_file"}
        )
        self.assertEqual(settings["decoration_file"], "builtin:star-trail.svg")
        options = birthday.render_options(
            ["千石由乃"], date(2026, 11, 4), birthday.PORTRAIT_PEOPLE, settings
        )
        self.assertEqual(options["label"], "千石由乃")
        self.assertEqual(options["date"], "2026.11.4")
        self.assertEqual(options["color"], "#EE5577")
        self.assertNotIn("Cooper", options["font_family"])

    def test_all_text_templates_and_custom_colors(self):
        settings = birthday.load_settings(
            {
                "date_format": "{year}-{month:02d}-{day:02d}",
                "greeting_template": "{name} 生日快乐",
                "label_template": "{name}",
                "subtitle_template": "饰 {character}",
                "date_template": "日期 {date}",
                "color": "#123456",
                "ring_colors": ["#112233", "#334455", "#556677"],
            },
            self.data,
        )
        options = birthday.render_options(
            ["反田叶月"], date(2026, 2, 28), birthday.PORTRAIT_PEOPLE, settings
        )
        self.assertEqual(options["label"], "反田叶月")
        self.assertEqual(options["subtitle"], "饰 纯田真奈")
        self.assertEqual(options["date"], "日期 2026-02-28")
        self.assertEqual(options["color"], "#123456")
        self.assertEqual(options["ring_colors"], settings["ring_colors"])

    def test_custom_group_formats(self):
        settings = birthday.load_settings(
            {
                "base_group_name": "原名@常驻",
                "birthday_name_format": "【{names}生日】{base} · {date}",
                "normal_name_format": "{base} · 日常",
                "name_separator": "、",
            },
            self.data,
        )
        calendar = {"11-04": ["甲", "乙"]}
        self.assertEqual(
            birthday.group_name_for_day(
                "已修改", date(2026, 11, 4), calendar, settings
            ),
            "【甲、乙生日】原名@常驻 · 2026.11.4",
        )
        self.assertEqual(
            birthday.group_name_for_day(
                "已修改", date(2026, 11, 5), calendar, settings
            ),
            "原名@常驻 · 日常",
        )

    def test_invalid_configuration_rejected(self):
        cases = [
            {"date_format": "{date}"},
            {"label_template": "{unknown}"},
            {"label_template": "{name.__class__}"},
            {"label_template": "{"},
            {"color": "red"},
            {"ring_colors": ["#FFFFFF"]},
            {"avatar_radius": 500},
            {"outline_width": -1},
            {"label_size": 0},
            {"font_weight": 1000},
        ]
        for rule in cases:
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                birthday.load_settings(rule, self.data)

    def test_user_assets_and_file_replacement(self):
        (self.data / "files").mkdir()
        file = self.data / "files/icon.svg"
        file.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        rule = {"decoration_file": "icon.svg"}
        first = birthday.load_settings(rule, self.data, ["files/icon.svg"])
        options = birthday.render_options(["甲"], date(2026, 1, 1), {}, first)
        self.assertTrue(
            options["asset_data"]["decoration_file"].startswith(
                "data:image/svg+xml;base64,"
            )
        )
        file.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
        )
        second = birthday.load_settings(rule, self.data, ["files/icon.svg"])
        self.assertNotEqual(first["assets"], second["assets"])
        with self.assertRaises(ValueError):
            birthday.load_settings({"font_file": "files/icon.svg"}, self.data)
        with self.assertRaises(FileNotFoundError):
            birthday.load_settings({"font_file": "missing.ttf"}, self.data)
        with self.assertRaises(ValueError):
            birthday.load_settings({"decoration_file": "../escape.svg"}, self.data)

    async def test_style_change_refreshes_once(self):
        from unittest.mock import AsyncMock

        folder = self.data / "avatars/test/123"
        folder.mkdir(parents=True)
        (folder / "original.jpg").write_bytes(b"original")
        rule = {
            "platform_id": "test",
            "group_id": 123,
            "avatar_enabled": True,
            "zone": ZoneInfo("Asia/Tokyo"),
            "birthdays": {"11-04": ["千石由乃"]},
            "presentation": birthday.load_settings({}, self.data),
        }

        async def render(original, output, names, day, settings):
            output.write_bytes(b"rendered")

        client = Client()
        with patch.object(birthday, "render_portrait", AsyncMock(side_effect=render)):
            await birthday.sync_group_portrait(
                client, rule, date(2026, 11, 4), self.data
            )
            rule["presentation"] = birthday.load_settings(
                {"label_template": "{display_name}"}, self.data
            )
            await birthday.sync_group_portrait(
                client, rule, date(2026, 11, 4), self.data
            )
            await birthday.sync_group_portrait(
                client, rule, date(2026, 11, 4), self.data
            )
        self.assertEqual(len(client.calls), 2)

    async def test_custom_group_name_does_not_accumulate_suffix(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        current = "同好群@千石由乃生日快乐"

        async def call(action, **params):
            nonlocal current
            if action == "get_group_info":
                return {"group_name": current}
            if action == "set_group_name":
                current = params["group_name"]

        client = SimpleNamespace(call_action=call)
        platform = SimpleNamespace(
            meta=lambda: SimpleNamespace(id="test"),
            get_client=lambda client=client: client,
        )
        plugin = object.__new__(birthday.BanGDreamBirthdayPlugin)
        plugin.context = SimpleNamespace(
            platform_manager=SimpleNamespace(platform_insts=[platform])
        )
        rule = {
            "platform_id": "test",
            "group_id": 123,
            "zone": ZoneInfo("Asia/Tokyo"),
            "birthdays": {"11-04": ["千石由乃"]},
            "presentation": birthday.load_settings(
                {"birthday_name_format": "{base}【{name}】"}, self.data
            ),
        }
        with (
            patch.object(birthday.StarTools, "get_data_dir", return_value=self.data),
            patch.object(birthday, "sync_group_portrait", AsyncMock()),
        ):
            await plugin.sync_group_name(rule, date(2026, 11, 4))
            await plugin.sync_group_name(rule, date(2026, 11, 4))
            self.assertEqual(current, "同好群【千石由乃】")
            await plugin.sync_group_name(rule, date(2026, 11, 5))
            self.assertEqual(current, "同好群")


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_success_and_repeat(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        for enabled in [False, True]:
            with tempfile.TemporaryDirectory() as temp:
                current = "测试群"
                messages = []

                async def call(action, messages=messages, **params):
                    nonlocal current
                    if action == "get_group_info":
                        return {"group_name": current}
                    if action == "set_group_name":
                        current = params["group_name"]
                    if action == "send_group_msg":
                        messages.append(params["message"])

                client = SimpleNamespace(call_action=call)
                platform = SimpleNamespace(
                    meta=lambda: SimpleNamespace(id="test"),
                    get_client=lambda client=client: client,
                )
                plugin = object.__new__(birthday.BanGDreamBirthdayPlugin)
                plugin.context = SimpleNamespace(
                    platform_manager=SimpleNamespace(platform_insts=[platform])
                )
                rule = {
                    "platform_id": "test",
                    "group_id": 123,
                    "zone": ZoneInfo("Asia/Tokyo"),
                    "birthdays": {"11-04": ["千石由乃"]},
                    "presentation": birthday.load_settings(
                        {"notify_enabled": enabled}, Path(temp)
                    ),
                }
                with (
                    patch.object(
                        birthday.StarTools, "get_data_dir", return_value=Path(temp)
                    ),
                    patch.object(
                        birthday,
                        "sync_group_portrait",
                        AsyncMock(side_effect=[True, False]),
                    ),
                ):
                    await plugin.sync_group_name(rule, date(2026, 11, 4))
                    await plugin.sync_group_name(rule, date(2026, 11, 4))
                self.assertEqual(
                    messages,
                    [[{"type": "text", "data": {"text": "已更新群名和头像。"}}]]
                    if enabled
                    else [],
                )


unittest.main()
