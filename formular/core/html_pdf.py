"""Optional local-file HTML print used only outside the public Space image."""

from __future__ import annotations

import pathlib
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from playwright.async_api import async_playwright


async def render_html_to_pdf(input_path: str, output_path: str) -> None:
    async with async_playwright() as printer:
        browser = await printer.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            allowed_root = pathlib.Path(input_path).resolve().parent

            async def local_resources_only(route):
                request_url = route.request.url
                if request_url.startswith(("data:", "blob:", "about:")):
                    await route.continue_()
                    return
                if request_url.startswith("file:"):
                    candidate = pathlib.Path(
                        url2pathname(unquote(urlsplit(request_url).path))
                    ).resolve()
                    try:
                        candidate.relative_to(allowed_root)
                    except ValueError:
                        await route.abort()
                        return
                    await route.continue_()
                    return
                await route.abort()

            await page.route("**/*", local_resources_only)
            file_uri = pathlib.Path(input_path).resolve().as_uri()
            await page.goto(file_uri, wait_until="load")
            await page.add_style_tag(
                content=(
                    "body { max-width: none !important; padding: 0 !important; "
                    "margin: 0 !important; } body > *:first-child { margin-top: 0 !important; }"
                )
            )
            await page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "1in", "right": "1in", "bottom": "1in", "left": "1in"},
            )
        finally:
            await browser.close()
