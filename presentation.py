import base64
import json
import re
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).parent
KEYS = (
    "notify_enabled",
    "notify_template",
    "base_group_name",
    "birthday_name_format",
    "normal_name_format",
    "name_separator",
    "date_format",
    "greeting_template",
    "date_template",
    "label_template",
    "subtitle_template",
    "font_family",
    "cjk_font_family",
    "font_file",
    "cjk_font_file",
    "font_weight",
    "greeting_size",
    "date_size",
    "label_size",
    "label_spacing",
    "subtitle_size",
    "color",
    "ring_colors",
    "greeting_color",
    "date_color",
    "label_color",
    "subtitle_color",
    "outline_color",
    "outline_width",
    "background_color",
    "show_avatar",
    "avatar_radius",
    "top_angle",
    "bottom_angle",
    "decoration_file",
    "decoration_size",
)
SCHEMA = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))[
    "group_rules"
]["templates"]["group"]["items"]
DEFAULTS = {key: SCHEMA[key]["default"] for key in KEYS}
FIELDS = {
    "base",
    "name",
    "names",
    "display_name",
    "character",
    "date",
    "year",
    "month",
    "day",
    "spacing",
}
MIMES = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def validate_template(template, fields):
    for _, field, _, conversion in Formatter().parse(template):
        if field is not None and (field not in fields or conversion):
            raise ValueError(f"不支持的模板变量或转换：{field}")
    values = {key: 1 if key in {"year", "month", "day"} else "示例" for key in fields}
    template.format_map(values)


def load_settings(rule, data_dir, uploaded=()):
    settings = {key: rule.get(key, value) for key, value in DEFAULTS.items()}
    validate_template(settings["date_format"], {"year", "month", "day"})
    for key in [
        "birthday_name_format",
        "normal_name_format",
        "greeting_template",
        "date_template",
        "label_template",
        "subtitle_template",
    ]:
        validate_template(settings[key], FIELDS)
    for key in [
        "color",
        "greeting_color",
        "date_color",
        "label_color",
        "subtitle_color",
        "outline_color",
        "background_color",
    ]:
        value = settings[key]
        if (key == "background_color" and value == "transparent") or (
            not value and key not in {"outline_color", "background_color"}
        ):
            continue
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"{key} 须为 #RRGGBB 色号")
    palette = settings["ring_colors"]
    if palette and (
        len(palette) != 3
        or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", value) for value in palette)
    ):
        raise ValueError("ring_colors 须为空或包含三个 #RRGGBB 色号")
    limits = {
        "font_weight": (100, 900),
        "label_spacing": (0, 24),
        "avatar_radius": (256, 448),
        "outline_width": (0, 24),
        "top_angle": (-180, 180),
        "bottom_angle": (-180, 180),
        "decoration_size": (8, 192),
    }
    limits.update(
        {
            key: (1, 256)
            for key in ["greeting_size", "date_size", "label_size", "subtitle_size"]
        }
    )
    for key, (low, high) in limits.items():
        value = settings[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise ValueError(f"{key} 须为 {low}～{high} 的整数")
    validate_template(settings["notify_template"], FIELDS | {"action", "group_name"})
    files = {Path(name).name: data_dir / name for name in uploaded}
    assets = {}
    for key in ["font_file", "cjk_font_file", "decoration_file"]:
        name = settings[key]
        if not name:
            continue
        if name.startswith("builtin:"):
            bundled = {
                "font_file": "CooperBlack.ttf",
                "cjk_font_file": "KNBobohei-Bold.ttf",
                "decoration_file": "star-trail.svg",
            }
            if name != "builtin:" + bundled[key]:
                raise ValueError("未知的内置素材")
            path = ROOT / "assets" / bundled[key]
        else:
            path = files.get(name, data_dir / name).resolve()
            if not path.is_relative_to(data_dir.resolve()):
                raise ValueError("字体或装饰图必须位于本插件数据目录内")
        allowed = (
            {".png", ".jpg", ".jpeg", ".webp", ".svg"}
            if key == "decoration_file"
            else {".ttf", ".otf", ".woff", ".woff2"}
        )
        if path.suffix.lower() not in allowed:
            raise ValueError(f"{key} 文件格式不支持")
        stat = path.stat()
        assets[key] = {
            "path": str(path),
            "size": stat.st_size,
            "modified": stat.st_mtime_ns,
        }
    settings["assets"] = assets
    return settings


def template_values(names, birthday, people, settings, base=""):
    persons = [people.get(name, {"name": name}) for name in names]
    values = {"year": birthday.year, "month": birthday.month, "day": birthday.day}
    values.update(
        {
            "date": settings["date_format"].format_map(values),
            "base": base,
            "names": settings["name_separator"].join(names),
            "name": names[0] if names else "",
            "display_name": settings["name_separator"].join(
                p.get("display_name", p["name"]) for p in persons
            ),
            "character": settings["name_separator"].join(
                p.get("character", p["name"]) for p in persons
            ),
            "spacing": " " if len(names) > 1 else "",
        }
    )
    return values


def render_options(names, birthday, people, settings):
    values = template_values(names, birthday, people, settings)
    options = dict(settings)
    options["color"] = settings["color"] or people.get(names[0], {}).get(
        "color", "#EE5577"
    )
    for field in ["greeting", "date", "label", "subtitle"]:
        options[field] = settings[field + "_template"].format_map(values)
    options["asset_data"] = {}
    for key, asset in settings.get("assets", {}).items():
        path = Path(asset["path"])
        options["asset_data"][key] = (
            "data:"
            + MIMES[path.suffix.lower()]
            + ";base64,"
            + base64.b64encode(path.read_bytes()).decode("ascii")
        )
    options.pop("assets", None)
    return options
