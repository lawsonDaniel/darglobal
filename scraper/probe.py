import sys, asyncio
from playwright.async_api import async_playwright
async def main(urls, headless):
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=headless, channel=("chrome" if not headless else None))
        ctx = await b.new_context(locale="en-US", viewport={"width":1366,"height":900})
        pg = await ctx.new_page()
        for u in urls:
            try:
                await pg.goto(u, wait_until="domcontentloaded", timeout=45000)
                await pg.wait_for_timeout(8000)
                t = await pg.title(); txt = await pg.inner_text("body")
                print("==", u, "|", pg.url, "|", t, "|", len(txt)); print(txt[:500].replace("\n"," / "))
            except Exception as e: print("ERR", u, e)
        await b.close()
asyncio.run(main(sys.argv[2:], sys.argv[1]=="1"))
