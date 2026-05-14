"""
scraper.py
==========
Playwright-based scraper for ekantipur.com
Extracts:
  1. Top 5 Entertainment (मनोरञ्जन) news articles
  2. Cartoon of the Day (व्यङ्ग्यचित्र / गाईजात्रे)

Author  : Data Extraction Intern Candidate
Requires: Python 3.11+, playwright, uv
Run via : uv run python scraper.py
"""

import json
import re
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─── Constants ────────────────────────────────────────────────────────────────
BASE_URL         = "https://ekantipur.com"
ENTERTAINMENT_URL = f"{BASE_URL}/entertainment"
OUTPUT_FILE      = "output.json"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_absolute(url: str) -> str:
    """Convert a relative URL to an absolute one."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE_URL + url
    return url


def safe_text(element, selector: str) -> str | None:
    """Safely extract text from a child element; return None if not found."""
    try:
        el = element.query_selector(selector)
        if el:
            return el.text_content().strip() or None
    except Exception:
        pass
    return None


def safe_attr(element, selector: str, attr: str) -> str | None:
    """Safely extract an attribute from a child element; return None if not found."""
    try:
        el = element.query_selector(selector)
        if el:
            val = el.get_attribute(attr)
            return val.strip() if val else None
    except Exception:
        pass
    return None


def get_best_image_src(img_el) -> str | None:
    """
    Try multiple attributes for the real image URL.
    Many news sites use lazy-loading (data-src, data-lazy-src, srcset).
    """
    if not img_el:
        return None
    for attr in ["data-src", "data-lazy-src", "data-original", "src"]:
        val = img_el.get_attribute(attr)
        if val and not val.endswith("placeholder") and "data:image" not in val:
            return make_absolute(val.strip())
    # Fall back to srcset first entry
    srcset = img_el.get_attribute("srcset")
    if srcset:
        first = srcset.split(",")[0].split(" ")[0].strip()
        return make_absolute(first)
    return None


# ─── Task 1: Entertainment News ───────────────────────────────────────────────

def extract_entertainment_news(page) -> list[dict]:
    """
    Navigate to the Entertainment section and extract the top 5 articles.
    Returns a list of dicts with keys: title, image_url, category, author.
    """
    print("\n[1/2] Navigating to Entertainment section...")

    # Try the direct English URL first; fall back to clicking the nav link
    try:
        page.goto(ENTERTAINMENT_URL, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        print("  Direct URL timed out — trying homepage nav link...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        # Click the मनोरञ्जन nav link
        try:
            page.click("text=मनोरञ्जन", timeout=10_000)
        except PlaywrightTimeout:
            print("  Could not find मनोरञ्जन link in nav. Aborting.")
            return []

    # Wait for article cards to appear — try several common selectors
    article_selectors = [
        ".news-archive article",
        ".archive-news article",
        "article.normal",
        ".story-list article",
        ".news-list .item",
        "article",                     # broad fallback
    ]

    cards = []
    for sel in article_selectors:
        try:
            page.wait_for_selector(sel, timeout=10_000)
            cards = page.query_selector_all(sel)
            if cards:
                print(f"  Found {len(cards)} article cards with selector: {sel!r}")
                break
        except PlaywrightTimeout:
            continue

    if not cards:
        # Debug: dump page title and first 500 chars of HTML so you can inspect
        print("  WARNING: No article cards found. Page title:", page.title())
        print("  HTML preview:", page.content()[:800])
        return []

    results = []
    for card in cards[:5]:
        # ── Title ────────────────────────────────────────────────────────────
        title = (
            safe_text(card, "h2 a")
            or safe_text(card, "h3 a")
            or safe_text(card, "h2")
            or safe_text(card, "h3")
            or safe_text(card, ".title")
            or safe_text(card, "a")
        )

        # ── Image URL ─────────────────────────────────────────────────────────
        img_el = card.query_selector("img")
        image_url = get_best_image_src(img_el)

        # Some sites wrap image in a picture tag — try source srcset
        if not image_url:
            source_el = card.query_selector("picture source")
            if source_el:
                srcset = source_el.get_attribute("srcset") or ""
                image_url = make_absolute(srcset.split(",")[0].split(" ")[0].strip())

        # ── Category ──────────────────────────────────────────────────────────
        category = (
            safe_text(card, ".cat")
            or safe_text(card, ".category")
            or safe_text(card, ".section")
            or safe_text(card, "span.cat-name")
            or safe_text(card, ".label")
            or "मनोरञ्जन"   # default for this section
        )

        # ── Author ────────────────────────────────────────────────────────────
        author = (
            safe_text(card, ".author")
            or safe_text(card, ".reporter")
            or safe_text(card, "[class*='author']")
            or safe_text(card, "[class*='reporter']")
            or safe_text(card, "span.name")
        )

        results.append({
            "title":     title,
            "image_url": image_url,
            "category":  category,
            "author":    author,
        })

        print(f"  ✓ Article: {(title or 'N/A')[:60]}")

    return results


# ─── Task 2: Cartoon of the Day ───────────────────────────────────────────────

def extract_cartoon(page) -> dict | None:
    """
    Find the 'Cartoon of the Day' section on the homepage and extract it.
    Returns a dict with keys: title, image_url, author. Returns None on failure.
    """
    print("\n[2/2] Looking for Cartoon of the Day...")

    # Go back to the homepage where the cartoon widget usually lives
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)

    # Strategy 1: find section/div containing the Nepali label for "cartoon"
    # Possible labels: व्यङ्ग्यचित्र, ग्यात्र, गाईजात्रे, Cartoon
    cartoon_labels = [
        "व्यङ्ग्यचित्र",
        "ग्यात्र",
        "गाईजात्रे",
        "cartoon",
        "Cartoon",
    ]

    cartoon_container = None

    # Try to find a heading/label element that contains one of the cartoon keywords
    for label in cartoon_labels:
        try:
            # Playwright's text= selector is case-insensitive partial match with >>
            heading = page.query_selector(f"text={label}")
            if heading:
                # Walk up the DOM to find the containing section
                # We use the heading's closest ancestor that looks like a widget
                cartoon_container = page.evaluate(
                    """(el) => {
                        // Climb up until we find a section or div with an image child
                        let node = el;
                        for (let i = 0; i < 8; i++) {
                            if (!node.parentElement) break;
                            node = node.parentElement;
                            if (node.querySelector('img')) return node.outerHTML;
                        }
                        return null;
                    }""",
                    heading,
                )
                if cartoon_container:
                    print(f"  Found cartoon section via label: {label!r}")
                    break
        except Exception:
            continue

    # Strategy 2: look for dedicated section selectors
    if not cartoon_container:
        container_selectors = [
            ".cartoon-of-day",
            ".cartoon",
            "[class*='cartoon']",
            ".caricature",
            ".gaaijaatre",          # transliteration
        ]
        for sel in container_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    cartoon_container = el.inner_html()
                    print(f"  Found cartoon section via selector: {sel!r}")
                    break
            except Exception:
                continue

    # Strategy 3: look inside sidebar widgets for cartoon
    if not cartoon_container:
        widgets = page.query_selector_all(".widget, .sidebar .box, aside .section")
        for widget in widgets:
            text = widget.text_content() or ""
            if any(label in text for label in cartoon_labels):
                cartoon_container = widget
                print("  Found cartoon section inside sidebar widget.")
                break

    # ── If we found the container HTML string, re-query the actual element ────
    # Re-find the container as a live element using page locators
    cartoon_el = None
    for label in cartoon_labels:
        try:
            # Use Playwright locator: find ancestor of the label that contains an img
            loc = page.locator(f"text={label}").locator("xpath=ancestor::div[.//img][1]")
            if loc.count() > 0:
                cartoon_el = loc.first.element_handle()
                break
        except Exception:
            continue

    if not cartoon_el:
        # Try the direct class selectors as element handles
        for sel in ["[class*='cartoon']", ".caricature", ".gaaijaatre"]:
            try:
                el = page.query_selector(sel)
                if el:
                    cartoon_el = el
                    break
            except Exception:
                continue

    if not cartoon_el:
        print("  WARNING: Cartoon section not found on homepage.")
        print("  Trying /cartoon page as fallback...")
        try:
            page.goto(f"{BASE_URL}/cartoon", wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_selector("article, .cartoon-item, .news-item", timeout=10_000)
            cartoon_el = (
                page.query_selector("article")
                or page.query_selector(".cartoon-item")
                or page.query_selector(".news-item")
            )
        except PlaywrightTimeout:
            pass

    if not cartoon_el:
        print("  ERROR: Could not locate cartoon section.")
        return None

    # ── Extract data from the cartoon element ─────────────────────────────────
    img_el   = cartoon_el.query_selector("img")
    image_url = get_best_image_src(img_el)

    title = (
        safe_text(cartoon_el, "h2 a")
        or safe_text(cartoon_el, "h3 a")
        or safe_text(cartoon_el, "h2")
        or safe_text(cartoon_el, "h3")
        or safe_text(cartoon_el, ".title")
        or safe_text(cartoon_el, "figcaption")
        or safe_text(cartoon_el, "a")
        or (img_el.get_attribute("alt") if img_el else None)
    )

    author = (
        safe_text(cartoon_el, ".author")
        or safe_text(cartoon_el, ".reporter")
        or safe_text(cartoon_el, ".cartoonist")
        or safe_text(cartoon_el, "[class*='author']")
        or safe_text(cartoon_el, "cite")
        or safe_text(cartoon_el, "figcaption")
    )

    print(f"  ✓ Cartoon title : {(title or 'N/A')[:60]}")
    print(f"  ✓ Cartoon author: {author or 'N/A'}")

    return {
        "title":     title,
        "image_url": image_url,
        "author":    author,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Ekantipur.com Data Extractor")
    print("=" * 60)

    output = {
        "entertainment_news":  [],
        "cartoon_of_the_day":  None,
    }

    with sync_playwright() as pw:
        # Launch Chromium — set headless=False to watch it run (great for debugging)
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            # Pretend to be a normal browser to avoid bot detection
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ne-NP",          # Nepali locale helps load correct content
        )
        page = context.new_page()

        # Block unnecessary resources to speed things up
        page.route(
            "**/*.{woff,woff2,ttf,otf,eot}",
            lambda route: route.abort()
        )

        try:
            # Task 1 — Entertainment news
            output["entertainment_news"] = extract_entertainment_news(page)

            # Task 2 — Cartoon of the day
            output["cartoon_of_the_day"] = extract_cartoon(page)

        except Exception as e:
            print(f"\n  FATAL ERROR: {e}")
            # Take a screenshot for debugging
            page.screenshot(path="error_screenshot.png")
            print("  Screenshot saved to error_screenshot.png")

        finally:
            browser.close()

    # ── Validate ──────────────────────────────────────────────────────────────
    news_count = len(output["entertainment_news"])
    cartoon_ok = output["cartoon_of_the_day"] is not None
    print(f"\n{'='*60}")
    print(f"  Extraction complete!")
    print(f"  Entertainment articles : {news_count}/5")
    print(f"  Cartoon of the Day     : {'✓' if cartoon_ok else '✗ (not found)'}")
    print(f"{'='*60}")

    if news_count < 5:
        print(
            "\n  ⚠  WARNING: Fewer than 5 articles found.\n"
            "  Open the browser (headless=False) and press F12 to inspect\n"
            "  the actual class names, then update the selectors in\n"
            "  extract_entertainment_news() accordingly.\n"
        )

    # ── Write output.json with proper Nepali (Devanagari) encoding ────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  ✅ Data saved to {OUTPUT_FILE}\n")

    # Pretty-print to terminal for quick verification
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
