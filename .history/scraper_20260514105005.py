import json
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL          = "https://ekantipur.com"
ENTERTAINMENT_URL = f"{BASE_URL}/entertainment"
OUTPUT_FILE       = "output.json"
TIMEOUT           = 60_000  # 60 seconds

def make_absolute(url: str) -> str:
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
    try:
        el = element.query_selector(selector)
        if el:
            text = el.text_content().strip()
            return text if text else None
    except Exception:
        pass
    return None


def safe_attr(element, selector: str, attr: str) -> str | None:
    try:
        el = element.query_selector(selector)
        if el:
            val = el.get_attribute(attr)
            return val.strip() if val else None
    except Exception:
        pass
    return None


def goto_page(page, url: str) -> bool:
    try:
        print(f"  → Loading: {url}")
        page.goto(url, wait_until="commit", timeout=TIMEOUT)
        time.sleep(5)  # wait for JS content to render
        print(f"    Title: {page.title()}")
        return True
    except PlaywrightTimeout:
        print(f"  ✗ Timed out on: {url}")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def scroll_to_load(page):
    for i in range(1, 5):
        page.evaluate(f"window.scrollTo(0, {i * 700})")
        time.sleep(0.8)
    page.evaluate("window.scrollTo(0, 0)")  
    time.sleep(1)


def extract_entertainment_news(page) -> list[dict]:
    print("\n[Task 1] Extracting Entertainment News...")
    print("-" * 50)

    # Load the entertainment section
    ok = goto_page(page, ENTERTAINMENT_URL)
    if not ok:
        print("  ✗ Failed to load entertainment page.")
        return []

    # Scroll so all content loads
    scroll_to_load(page)

    # ── Find all article cards ─────────────────────────────────────────────
    # Each article is a div.category inside div.category-wrapper
    # We use ".category-wrapper .category" to avoid other stray .category elements
    cards = page.query_selector_all(".category-wrapper .category")

    print(f"  Found {len(cards)} article cards")

    if not cards:
        print("  ✗ No cards found. Run debug.py again to inspect the page.")
        return []

    results = []

    for i, card in enumerate(cards[:5]):  # only take first 5
        # ── Title ─────────────────────────────────────────────────────────
        # The title is inside .category-description → h2 → a
        title = (
            safe_text(card, ".category-description h2 a") or
            safe_text(card, "h2 a") or
            safe_text(card, "h2")
        )

        # ── Image URL ─────────────────────────────────────────────────────
        # Image is inside .category-image → figure → img
        # The site uses a plain src= attribute (no lazy loading on this page)
        image_url = (
            safe_attr(card, ".category-image img", "src")   or
            safe_attr(card, ".category-image img", "data-src") or
            safe_attr(card, "img", "src")
        )
        image_url = make_absolute(image_url)

        # ── Category ──────────────────────────────────────────────────────
        # The category label is in the page header, not each card.
        # Since we're on the entertainment section, we hardcode "मनोरञ्जन"
        # and also try to read any inline category label if present.
        category = (
            safe_text(card, ".category-name") or
            safe_text(card, ".cat")           or
            "मनोरञ्जन"  # default — we are on the entertainment page
        )

        # ── Author ────────────────────────────────────────────────────────
        # Author is in div.author-name → p → a
        author = (
            safe_text(card, ".author-name a") or
            safe_text(card, ".author-name")   or
            safe_text(card, ".reporter")
        )

        results.append({
            "title":     title,
            "image_url": image_url,
            "category":  category,
            "author":    author,
        })

        print(f"  [{i+1}] {(title or 'No title')[:65]}")
        print(f"       Author   : {author or 'null'}")
        print(f"       Image    : {'✓' if image_url else '✗ not found'}")

    return results


# ── Task 2: Cartoon of the Day ─────────────────────────────────────────────────

def extract_cartoon(page) -> dict | None:
    """
    Find the Cartoon of the Day on the ekantipur homepage.

    The cartoon section was NOT found with 'cartoon' in class names,
    so we search by Nepali text labels and DOM structure.
    We also try the /cartoon direct URL as a fallback.
    """
    print("\n[Task 2] Extracting Cartoon of the Day...")
    print("-" * 50)

    # ── Try homepage first ─────────────────────────────────────────────────
    ok = goto_page(page, BASE_URL)
    if not ok:
        print("  ✗ Failed to load homepage.")
        return None

    scroll_to_load(page)

    # ── Search by Nepali cartoon label text ───────────────────────────────
    # Possible Nepali labels for "cartoon": व्यङ्ग्यचित्र, ग्यात्र, कार्टुन
    cartoon_labels = ["व्यङ्ग्यचित्र", "ग्यात्र", "कार्टुन", "cartoon", "Cartoon"]
    cartoon_el     = None

    for label in cartoon_labels:
        try:
            label_el = page.query_selector(f"text={label}")
            if not label_el:
                continue

            print(f"  Found text label: '{label}'")

            # Walk UP the DOM tree to find an ancestor that contains an <img>
            # This gives us the whole cartoon widget/section
            ancestor = page.evaluate_handle(
                """(el) => {
                    let node = el;
                    for (let i = 0; i < 12; i++) {
                        if (!node.parentElement) break;
                        node = node.parentElement;
                        if (node.querySelector('img')) return node;
                    }
                    return null;
                }""",
                label_el
            )

            el = ancestor.as_element()
            if el:
                cartoon_el = el
                print(f"  ✓ Found cartoon container via label '{label}'")
                break

        except Exception as e:
            print(f"  Label '{label}' error: {e}")
            continue

    # ── Fallback: try /cartoon page ────────────────────────────────────────
    if not cartoon_el:
        print("  Not found on homepage. Trying /cartoon page...")
        ok = goto_page(page, f"{BASE_URL}/cartoon")
        if ok:
            scroll_to_load(page)

            # On the cartoon archive page, each cartoon is a .category div
            # (same structure as entertainment — same site template)
            card = (
                page.query_selector(".category-wrapper .category") or
                page.query_selector(".category-inner-wrapper")      or
                page.query_selector("article")
            )
            if card:
                cartoon_el = card
                print("  ✓ Found cartoon on /cartoon page")

    if not cartoon_el:
        print("  ✗ Cartoon section not found on homepage or /cartoon page.")
        print("    Run debug_cartoon.py to inspect the homepage structure.")
        return None

    # ── Extract data from the cartoon container ────────────────────────────
    img_el    = cartoon_el.query_selector("img")

    # Get image URL — try src first, then data-src for lazy loading
    image_url = None
    if img_el:
        image_url = (
            img_el.get_attribute("src")       or
            img_el.get_attribute("data-src")  or
            img_el.get_attribute("data-lazy-src")
        )
        image_url = make_absolute(image_url)

    # Get title
    title = (
        safe_text(cartoon_el, ".category-description h2 a") or
        safe_text(cartoon_el, "h2 a")         or
        safe_text(cartoon_el, "h2")           or
        safe_text(cartoon_el, "h3")           or
        safe_text(cartoon_el, ".title")       or
        safe_text(cartoon_el, "figcaption")   or
        (img_el.get_attribute("alt").strip() if img_el else None)
    )

    # Get author
    author = (
        safe_text(cartoon_el, ".author-name a") or
        safe_text(cartoon_el, ".author-name")   or
        safe_text(cartoon_el, ".author")         or
        safe_text(cartoon_el, ".reporter")       or
        safe_text(cartoon_el, "cite")
    )

    print(f"  ✓ Title : {(title  or 'null')[:65]}")
    print(f"  ✓ Author: {author or 'null'}")
    print(f"  ✓ Image : {'✓' if image_url else '✗ not found'}")

    return {
        "title":     title,
        "image_url": image_url,
        "author":    author,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Ekantipur.com Data Extractor")
    print("=" * 60)

    output = {
        "entertainment_news": [],
        "cartoon_of_the_day": None,
    }

    with sync_playwright() as pw:
        # Launch Chrome — visible so you can watch it work
        browser = pw.chromium.launch(headless=False, slow_mo=400)
        context = browser.new_context(
            # Pretend to be a real Chrome browser
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            output["entertainment_news"] = extract_entertainment_news(page)
            output["cartoon_of_the_day"] = extract_cartoon(page)

        except Exception as e:
            print(f"\n  FATAL ERROR: {e}")

        finally:
            print("\n  Closing browser...")
            browser.close()

    # ── Print summary ──────────────────────────────────────────────────────
    news_count = len(output["entertainment_news"])
    cartoon_ok = output["cartoon_of_the_day"] is not None

    print(f"\n{'='*60}")
    print(f"  Entertainment articles : {news_count}/5")
    print(f"  Cartoon of the Day     : {'✓ Found' if cartoon_ok else '✗ Not found'}")
    print(f"{'='*60}")

    # ── Save to output.json ────────────────────────────────────────────────
    # ensure_ascii=False keeps Nepali Devanagari characters readable
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n Saved to {OUTPUT_FILE}\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()