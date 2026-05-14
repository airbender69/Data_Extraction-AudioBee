"""
debug.py
========
Run this to print the actual HTML structure of ekantipur.com
so we can find the correct CSS selectors.

Run: uv run python debug.py
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://ekantipur.com"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()

    # ── Load entertainment page ────────────────────────────────────────────
    print("Loading entertainment page...")
    page.goto(f"{BASE_URL}/entertainment", wait_until="commit", timeout=60000)
    time.sleep(5)

    # Scroll to trigger lazy loading
    for i in range(4):
        page.evaluate(f"window.scrollTo(0, {(i+1) * 600})")
        time.sleep(1)

    print(f"\nURL   : {page.url}")
    print(f"Title : {page.title()}")

    # ── Print ALL unique class names found on the page ─────────────────────
    print("\n" + "="*60)
    print("ALL CLASS NAMES FOUND ON THE PAGE:")
    print("="*60)
    classes = page.evaluate("""
        () => {
            const all = document.querySelectorAll('*');
            const classSet = new Set();
            all.forEach(el => {
                el.classList.forEach(c => classSet.add(c));
            });
            return [...classSet].sort();
        }
    """)
    for c in classes:
        print(f"  .{c}")

    # ── Print the first article-like element's HTML ────────────────────────
    print("\n" + "="*60)
    print("FIRST <article> TAG HTML (if any):")
    print("="*60)
    art = page.query_selector("article")
    if art:
        print(art.inner_html()[:1500])
    else:
        print("  No <article> tags found on the page!")

    # ── Print body structure (first 3000 chars) ────────────────────────────
    print("\n" + "="*60)
    print("BODY HTML PREVIEW (first 3000 chars):")
    print("="*60)
    body = page.inner_html("body")
    print(body[:3000])

    # ── Check cartoon section ──────────────────────────────────────────────
    print("\n" + "="*60)
    print("CARTOON SECTION HTML:")
    print("="*60)
    cartoon = page.query_selector("[class*='cartoon']")
    if cartoon:
        print(cartoon.inner_html()[:1500])
    else:
        print("  No element with 'cartoon' in class name found!")

    input("\nPress Enter to close the browser...")
    browser.close()

print("\nDone! Copy the output above and share it.")
