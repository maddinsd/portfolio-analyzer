"""Stage 12: Playwright full audit — screenshots all pages, light+dark, 3 breakpoints."""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:5001"
PASSWORD = os.environ.get("ADMIN_TOKEN", "")
OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)

BREAKPOINTS = [
    ("desktop", 1440, 900),
    ("tablet",   768, 1024),
    ("mobile",   390, 844),
]

# Map (name, nav_text) for click-based SPA navigation
PAGES = [
    ("home",      "Home"),       # analyze page (the analysis tool)
    ("watchlist", "Watchlist"),  # dashboard/monitoring page
    ("lbo",       "LBO Calculator"),
    ("ma",        "M&A Builder"),
    ("notify",    "Notifications"),
    ("history",   "History"),
]

async def shot(page, name, theme, bp_name):
    path = OUT / f"{bp_name}_{theme}_{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"  ✓ {path.name}")

async def set_theme(page, theme):
    await page.evaluate(f"localStorage.setItem('lindner_theme', '{theme}')")
    await page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    await page.wait_for_timeout(250)

async def nav_to(page, nav_text):
    """Click a nav item by its label text."""
    locator = page.locator(".nav-item").filter(has_text=nav_text).first
    await locator.click()
    await page.wait_for_timeout(400)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        for bp_name, width, height in BREAKPOINTS:
            print(f"\n── {bp_name} ({width}×{height}) ──")
            ctx = await browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=2,
            )
            page = await ctx.new_page()

            # Capture login page before authenticating
            await page.goto(f"{BASE}/login", wait_until="networkidle")
            await shot(page, "login", "light", bp_name)

            # Authenticate
            await page.fill("input[name='password']", PASSWORD)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)

            for theme in ["light", "dark"]:
                print(f"  theme: {theme}")
                await set_theme(page, theme)

                # Start from home each theme pass
                await page.goto(f"{BASE}/", wait_until="networkidle")
                await page.wait_for_timeout(800)
                await page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
                await page.wait_for_timeout(200)

                # Navigate to each SPA page via nav clicks
                for page_name, nav_text in PAGES:
                    await nav_to(page, nav_text)
                    # Reapply theme (React state might have reset it)
                    await page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
                    await page.wait_for_timeout(150)
                    await shot(page, page_name, theme, bp_name)

            await ctx.close()

        await browser.close()
        print(f"\nAll screenshots saved to {OUT}")
        screenshots = sorted(OUT.glob("*.png"))
        print(f"Total: {len(screenshots)} files")

if __name__ == "__main__":
    asyncio.run(main())
