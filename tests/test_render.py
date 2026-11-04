import argparse
import asyncio
import base64
import importlib.util
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from playwright.async_api import async_playwright

parser = argparse.ArgumentParser()
parser.add_argument("plugin", type=Path)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--font", type=Path)
args = parser.parse_args()
root = args.plugin.resolve()
args.output.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location(
    "render_test_plugin", root / "main.py", submodule_search_locations=[str(root)]
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


async def main():
    with tempfile.TemporaryDirectory() as temp:
        data = Path(temp)
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1024, "height": 1024})
            await page.goto((root / "portrait.html").as_uri())
            people = {p["name"]: p for p in module.PORTRAIT_PEOPLE.values()}
            default = module.load_settings({}, data)
            for name, person in people.items():
                day = date.fromisoformat("2026-" + person["birthday"])
                options = module.render_options(
                    [name], day, module.PORTRAIT_PEOPLE, default
                )
                result = await page.evaluate(
                    """async ([names,options])=>{
                    options.background_color='transparent';
                    const svg=await render(null,names,options);
                    const img=new Image();img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);await img.decode();
                    const canvas=document.createElement('canvas');canvas.width=canvas.height=1024;
                    const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);const pixels=ctx.getImageData(0,0,1024,1024).data;
                    let overlap=0,outside=0;
                    for(let y=0;y<1024;y++)for(let x=0;x<1024;x++)if(pixels[(y*1024+x)*4+3]){
                        const d=(x+.5-512)**2+(y+.5-512)**2;if(d<(options.avatar_radius-1)**2)overlap++;if(d>510**2)outside++;
                    }
                    return {overlap,outside,decoration:!!document.querySelector('#decoration'),color:[...ctx.getImageData(20,512,1,1).data]};
                }""",
                    [[name], options],
                )
                expected = [int(person["color"][i : i + 2], 16) for i in (1, 3, 5)] + [
                    255
                ]
                assert result == {
                    "overlap": 0,
                    "outside": 0,
                    "decoration": True,
                    "color": expected,
                }, (name, result)
            image = await page.evaluate("""()=>{
                const c=document.createElement('canvas');c.width=c.height=1024;const x=c.getContext('2d');
                x.fillStyle='#e8f1f7';x.fillRect(0,0,1024,1024);x.fillStyle='#42718b';x.beginPath();x.arc(512,400,150,0,Math.PI*2);x.fill();
                x.beginPath();x.ellipse(512,870,310,260,0,0,Math.PI*2);x.fill();return c.toDataURL('image/jpeg');
            }""")
            original = data / "original.jpg"
            original.write_bytes(base64.b64decode(image.split(",")[1]))
            await module.render_portrait(
                original,
                args.output / "default.png",
                ["千石由乃"],
                date(2026, 11, 4),
                default,
            )
            (data / "badge.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="#ffcc00"/><circle cx="50" cy="50" r="20" fill="#ffffff"/></svg>'
            )
            rule = {
                "greeting_template": "生日快乐 {name}",
                "date_format": "{year}-{month:02d}-{day:02d}",
                "label_template": "{name}",
                "subtitle_template": "· HAPPY DAY",
                "greeting_color": "#123456",
                "outline_color": "#FFFFFF",
                "ring_colors": ["#AA3366", "#FFDDEE", "#772244"],
                "avatar_radius": 380,
                "top_angle": -4,
                "bottom_angle": 4,
                "decoration_file": "badge.svg",
            }
            if args.font:
                shutil.copyfile(args.font, data / args.font.name)
                rule["font_file"] = args.font.name
            settings = module.load_settings(rule, data)
            options = module.render_options(
                ["千石由乃"], date(2026, 11, 4), module.PORTRAIT_PEOPLE, settings
            )
            await page.evaluate(
                "([image,names,options])=>render(image,names,options)",
                [image, ["千石由乃"], options],
            )
            assert await page.locator("#greeting").text_content() == "生日快乐 千石由乃"
            assert await page.locator("#date-label").text_content() == "2026-11-04"
            assert await page.locator("#name-label").text_content() == "千石由乃"
            assert await page.locator("#subtitle").text_content() == "· HAPPY DAY"
            assert await page.locator("#photo circle").get_attribute("r") == "380"
            assert await page.locator("#decoration").count() == 1
            if args.font:
                assert await page.evaluate(
                    "document.fonts.check('800 64px \"Birthday Custom Latin\"')"
                )
            await page.screenshot(path=str(args.output / "custom.png"))
            settings = module.load_settings(
                {
                    "greeting_template": "",
                    "date_template": "",
                    "label_template": "",
                    "subtitle_template": "",
                    "show_avatar": False,
                },
                data,
            )
            options = module.render_options(
                ["自定义姓名"], date(2026, 11, 4), module.PORTRAIT_PEOPLE, settings
            )
            await page.evaluate(
                "([image,names,options])=>render(image,names,options)",
                [image, ["自定义姓名"], options],
            )
            assert await page.locator("text").count() == 0
            assert await page.locator("#original-avatar").count() == 0
            assert await page.locator("#rings circle").count() == 3
            await browser.close()
        print(
            f"PASS: {len(people)} default frames, exact character colors, no overlap/cropping; custom text/date/colors/font/image/layout and hidden elements. No QQ writes."
        )


asyncio.run(main())
