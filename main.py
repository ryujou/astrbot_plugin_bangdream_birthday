import asyncio
import base64
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import Context, Star, StarTools

from .presentation import DEFAULTS, load_settings, render_options, template_values

PLUGIN_ID = "astrbot_plugin_bangdream_birthday"
FRAME_VERSION = "chinese-star-20261104"


def load_portrait_people():
    catalog = json.loads(
        Path(__file__).with_name("character_colors.json").read_text(encoding="utf-8")
    )
    characters = {c["name"]: c for c in catalog["characters"]}
    people = {
        alias: c
        for c in characters.values()
        for alias in [c["name"], *c.get("aliases", [])]
    }
    for actor in catalog["voice_actors"]:
        character = characters[actor["character"]]
        people[actor["name"]] = dict(
            actor,
            color=character["color"],
            display_name=actor["name"],
            subtitle="饰 " + character["name"],
        )
    return people


PORTRAIT_PEOPLE = load_portrait_people()


def merge_calendar(target, source):
    for day, names in source.items():
        combined = target.setdefault(day, [])
        for name in names:
            if name not in combined:
                combined.append(name)


def calendar_from_rows(rows, source):
    columns = None
    calendar = {}
    skipped = 0
    for row_number, row in enumerate(rows, 1):
        if columns is None:
            headers = {
                str(value).strip().casefold(): i
                for i, value in enumerate(row)
                if value is not None
            }

            def column(*names, headers=headers):
                return next((headers[name] for name in names if name in headers), None)

            name = column("姓名", "角色名", "名字", "name", "中文全名")
            month = column("月份", "月", "month")
            day = column("日期", "日", "day")
            birthday = column("生日", "birthday", "date", "日期")
            if name is not None and (
                (month is not None and day is not None) or birthday is not None
            ):
                columns = (name, month, day, birthday)
            continue

        def value(index, row=row):
            return row[index] if index is not None and index < len(row) else None

        name_index, month_index, day_index, birthday_index = columns
        name = str(value(name_index) or "").strip()
        if not name:
            continue
        try:
            if month_index is not None and day_index is not None:
                month, day = value(month_index), value(day_index)
                if month in (None, "") and day in (None, ""):
                    skipped += 1
                    continue
                month = int(str(month).strip().removesuffix("月"))
                day = int(str(day).strip().removesuffix("日"))
            else:
                birthday = value(birthday_index)
                if birthday in (None, ""):
                    skipped += 1
                    continue
                if isinstance(birthday, date):
                    month, day = birthday.month, birthday.day
                else:
                    match = re.fullmatch(
                        r"(?:\d{4}[-/.年])?(\d{1,2})[-/.月](\d{1,2})日?",
                        str(birthday).strip(),
                    )
                    if match is None:
                        raise ValueError("生日须为月日，例如 10-27 或 10月27日")
                    month, day = map(int, match.groups())
            key = date(2000, month, day).strftime("%m-%d")
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{source} 第 {row_number} 行（{name}）：{error}"
            ) from error
        merge_calendar(calendar, {key: [name]})
    return calendar, skipped, columns is not None


def import_calendar(path):
    path = Path(path)
    calendar = {}
    skipped = 0
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in workbook:
                rows, missing, _ = calendar_from_rows(
                    sheet.iter_rows(values_only=True), f"{path.name}/{sheet.title}"
                )
                merge_calendar(calendar, rows)
                skipped += missing
        finally:
            workbook.close()
    elif path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            calendar, skipped, _ = calendar_from_rows(csv.reader(stream), path.name)
    else:
        raise ValueError(f"不支持的生日表格式：{path.suffix}，请上传 XLSX 或 UTF-8 CSV")
    if not calendar:
        raise ValueError(
            f"{path.name} 没有可导入的生日，请使用“姓名、生日”或“月份、日期、角色名”列"
        )
    return calendar, skipped


def load_group_rules(config, data_dir):
    imported = {
        Path(name).name: data_dir / name for name in config.get("import_files", [])
    }
    rules = []
    seen = set()
    for entry in config.get("group_rules", []):
        if not entry.get("enabled", True):
            continue
        rule = dict(entry)
        rule.setdefault("platform_id", "qq_private")
        rule.setdefault("avatar_enabled", True)
        rule["group_id"] = int(rule["group_id"])
        scope = (rule["platform_id"], rule["group_id"])
        if scope in seen:
            raise ValueError(f"同一平台的群 {rule['group_id']} 重复配置")
        seen.add(scope)
        rule["zone"] = ZoneInfo(rule.get("timezone", "Asia/Tokyo"))
        calendar = {}
        if rule.get("use_builtin_calendar", True):
            source = Path(__file__).with_name("birthdays.json")
            merge_calendar(calendar, json.loads(source.read_text(encoding="utf-8")))
        for name in rule.get("import_names", []):
            if name not in imported:
                raise ValueError(
                    f"群 {rule['group_id']} 的生日表 {name} 尚未上传，请先在“导入生日表”中上传"
                )
            rows, skipped = import_calendar(imported[name])
            merge_calendar(calendar, rows)
            logger.info(
                "群 %s 导入 %s：%s 条生日，跳过 %s 条空白生日",
                rule["group_id"],
                name,
                sum(map(len, rows.values())),
                skipped,
            )
        if not calendar:
            raise ValueError(f"群 {rule['group_id']} 请开启内置生日表或选择导入文件")
        rule["presentation"] = load_settings(
            rule, data_dir, config.get("asset_files", [])
        )
        rule["birthdays"] = calendar
        rules.append(rule)
    return rules


def group_name_for_day(current_name, today, birthdays, settings=None):
    settings = settings or DEFAULTS
    base = settings["base_group_name"] or current_name.partition("@")[0]
    names = birthdays.get(today.strftime("%m-%d"), [])
    values = template_values(names, today, PORTRAIT_PEOPLE, settings, base)
    template = (
        settings["birthday_name_format"] if names else settings["normal_name_format"]
    )
    return template.format_map(values)


async def render_portrait(original, output, names, birthday, settings=None):
    from playwright.async_api import async_playwright

    settings = settings or DEFAULTS
    options = render_options(names, birthday, PORTRAIT_PEOPLE, settings)
    image = "data:image/jpeg;base64," + base64.b64encode(original.read_bytes()).decode(
        "ascii"
    )
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1024, "height": 1024})
            await page.goto(Path(__file__).with_name("portrait.html").as_uri())
            await page.evaluate(
                "([image,names,options]) => render(image,names,options)",
                [image, names, options],
            )
            await page.screenshot(
                path=str(output),
                type="png",
                omit_background=options["background_color"] == "transparent",
            )
        finally:
            await browser.close()


def download_original(group_id, path):
    with urlopen(
        f"https://p.qlogo.cn/gh/{group_id}/{group_id}/0", timeout=30
    ) as response:
        path.write_bytes(response.read())


async def sync_group_portrait(client, rule, today, data_dir, now=None):
    directory = data_dir / "avatars" / rule["platform_id"] / str(rule["group_id"])
    state_path = directory / "active.json"
    names = (
        rule["birthdays"].get(today.strftime("%m-%d"), [])
        if rule.get("avatar_enabled", False)
        else []
    )
    active = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else None
    )
    settings = rule.get("presentation", DEFAULTS)
    desired = {"names": names}
    if names:
        if all(name in PORTRAIT_PEOPLE for name in names):
            now = now or datetime.now(rule["zone"])
            names = [names[now.hour % len(names)]]
        desired = {
            "names": names,
            "event": today.isoformat(),
            "template": FRAME_VERSION,
            "appearance": {
                k: v
                for k, v in settings.items()
                if k
                not in {
                    "base_group_name",
                    "birthday_name_format",
                    "normal_name_format",
                    "notify_enabled",
                    "notify_template",
                }
            },
        }
    if not names and active is None:
        return False
    if active == desired:
        return False
    original = directory / "original.jpg"
    if names:
        directory.mkdir(parents=True, exist_ok=True)
        if not original.exists():
            await asyncio.to_thread(download_original, rule["group_id"], original)
        target = directory / "birthday.png"
        await render_portrait(original, target, names, today, settings)
    else:
        target = original
    payload = "base64://" + base64.b64encode(target.read_bytes()).decode("ascii")
    await client.call_action(
        "set_group_portrait", group_id=rule["group_id"], file=payload, cache=0
    )
    if names:
        state_path.write_text(json.dumps(desired, ensure_ascii=False), encoding="utf-8")
    else:
        state_path.unlink()
    logger.info(
        "生日群头像已更新：%s → %s",
        rule["group_id"],
        "&".join(names) if names else "原头像",
    )
    return True


class BanGDreamBirthdayPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.rules = []
        self.task = None
        self.checked_days = {}

    async def initialize(self):
        self.rules = await asyncio.to_thread(
            load_group_rules, self.config, StarTools.get_data_dir(PLUGIN_ID)
        )
        if self.rules:
            self.task = asyncio.create_task(self.watch_birthdays())

    async def sync_group_name(self, rule, today):
        platform_id = rule["platform_id"]
        platform = next(
            (
                item
                for item in self.context.platform_manager.platform_insts
                if item.meta().id == platform_id
            ),
            None,
        )
        if platform is None:
            return False
        client = platform.get_client()
        group_id = rule["group_id"]
        settings = dict(rule.get("presentation", DEFAULTS))
        changes = []
        target_name = ""
        if rule.get("name_enabled", True):
            async with asyncio.timeout(30):
                info = await client.call_action(
                    "get_group_info", group_id=group_id, no_cache=True
                )
                current_name = info["group_name"]
                data = StarTools.get_data_dir(PLUGIN_ID)
                base_path = data / "group_names" / platform_id / f"{group_id}.txt"
                if not settings["base_group_name"]:
                    if (
                        settings["birthday_name_format"]
                        == DEFAULTS["birthday_name_format"]
                        and settings["normal_name_format"]
                        == DEFAULTS["normal_name_format"]
                    ):
                        settings["base_group_name"] = current_name.partition("@")[0]
                    else:
                        settings["base_group_name"] = (
                            base_path.read_text(encoding="utf-8")
                            if base_path.exists()
                            else current_name.partition("@")[0]
                        )
                target_name = group_name_for_day(
                    current_name, today, rule["birthdays"], settings
                )
                if target_name != current_name:
                    await client.call_action(
                        "set_group_name", group_id=group_id, group_name=target_name
                    )
                    info = await client.call_action(
                        "get_group_info", group_id=group_id, no_cache=True
                    )
                    if info["group_name"] != target_name:
                        raise RuntimeError("QQ 返回的群名与目标群名不一致")
                    changes.append("群名")
                    logger.info("生日群名已更新：%s → %s", group_id, target_name)
                base_path.parent.mkdir(parents=True, exist_ok=True)
                base_path.write_text(settings["base_group_name"], encoding="utf-8")
        async with asyncio.timeout(90):
            avatar_changed = await sync_group_portrait(
                client,
                rule,
                today,
                StarTools.get_data_dir(PLUGIN_ID),
                datetime.now(rule["zone"]),
            )
        if avatar_changed:
            changes.append("头像")
        if changes and settings["notify_enabled"]:
            async with asyncio.timeout(30):
                if not rule.get("name_enabled", True):
                    info = await client.call_action(
                        "get_group_info", group_id=group_id, no_cache=True
                    )
                    target_name = info["group_name"]
                names = rule["birthdays"].get(today.strftime("%m-%d"), [])
                values = template_values(
                    names, today, PORTRAIT_PEOPLE, settings, settings["base_group_name"]
                )
                values.update(action="和".join(changes), group_name=target_name)
                message = settings["notify_template"].format_map(values)
                if message.strip():
                    await client.call_action(
                        "send_group_msg",
                        group_id=group_id,
                        message=[{"type": "text", "data": {"text": message}}],
                    )
        return True

    async def watch_birthdays(self):
        while True:
            for rule in self.rules:
                scope = (rule["platform_id"], rule["group_id"])
                now = datetime.now(rule["zone"])
                today = now.date()
                hourly = rule.get("avatar_enabled") and (
                    len(rule["birthdays"].get(today.strftime("%m-%d"), [])) > 1
                )
                check_key = (today, now.hour) if hourly else today
                if check_key != self.checked_days.get(scope):
                    try:
                        if await self.sync_group_name(rule, today):
                            self.checked_days[scope] = check_key
                    except Exception:  # noqa: BLE001 -- 单群失败必须隔离，完整记录后下轮重试。
                        logger.exception("生日群名或头像更新失败：%s", rule["group_id"])
            await asyncio.sleep(30)

    async def terminate(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
