import os, sys, time, json, traceback, re
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
import requests

START_URLS = [
    "https://promo.flexavida.com/bloodsugarultra/index2",
    "https://promo.flexavida.com/bloodsugarultra/index3",
]

VALID_CHECKOUT_PATHS = ["/checkout", "/checkout2", "/bloodsugarultra/checkout"]
EXPECTED_CART_TEXT = os.getenv("EXPECTED_CART_TEXT", "Subscribe & Save").split(",")

CTA_SELECTOR = os.getenv("CTA_SELECTOR", "a[href*='checkout'], button[href*='checkout'], a.cta, button.cta")
LOADING_OVERLAY_SELECTOR = os.getenv("LOADING_OVERLAY_SELECTOR", ".loading, .loader, .spinner, [data-loading='true']")
CART_CONTAINER_SELECTOR = os.getenv("CART_CONTAINER_SELECTOR", "#cart, .cart, [data-cart]")
CHECKOUT_READY_SELECTOR = os.getenv("CHECKOUT_READY_SELECTOR", "[data-checkout-ready='true'], form[action*='payment'], iframe[src*='stripe'], #checkout")

PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT_MS", "20000"))
SPINNER_TIMEOUT = int(os.getenv("SPINNER_TIMEOUT_MS", "15000"))
HEADLESS_MODE = os.getenv("HEADLESS", "true").lower() == "true"
RUN_INTERVAL = int(os.getenv("RUN_INTERVAL_MINUTES", "5"))  # Run every 5 minutes by default

ALERT_WEBHOOK_URL = "https://n8n.primopromotions.com/webhook/alert"

def send_results(results: dict):
    """Send monitoring results to webhook on every run"""
    try:
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "status": "success" if results.get("ok") else "failure"
        }
        requests.post(ALERT_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Results sent to webhook: {results.get('status', 'unknown')}")
    except Exception as e:
        print(f"Failed to send results to webhook: {e}", file=sys.stderr)

def wait_for_spinner_to_clear(page):
    try:
        loc = page.locator(LOADING_OVERLAY_SELECTOR)
        if loc.count() > 0:
            page.wait_for_selector(LOADING_OVERLAY_SELECTOR, state="hidden", timeout=SPINNER_TIMEOUT)
    except PwTimeout:
        raise AssertionError("Spinner/loader never cleared")

def validate_pricing(page) -> float:
    """Extract and validate pricing from checkout page. Returns price as float."""
    page_content = page.content()
    
    # Look for price patterns like $29.99, $49.95, etc.
    price_patterns = [
        r'\$\s*(\d+(?:\.\d{2})?)',  # $29.99, $ 29.99
        r'price["\s]*:?["\s]*\$?\s*(\d+(?:\.\d{2})?)',  # price: $29.99
        r'total["\s]*:?["\s]*\$?\s*(\d+(?:\.\d{2})?)',  # total: $29.99
        r'amount["\s]*:?["\s]*\$?\s*(\d+(?:\.\d{2})?)',  # amount: $29.99
    ]
    
    found_prices = []
    for pattern in price_patterns:
        matches = re.findall(pattern, page_content, re.IGNORECASE)
        for match in matches:
            try:
                price = float(match)
                if price > 0:  # Only consider positive prices
                    found_prices.append(price)
            except ValueError:
                continue
    
    if not found_prices:
        return 0.0
    
    # Return the highest price found (likely the total)
    return max(found_prices)

def ensure_checkout_ready(page):
    from urllib.parse import urlparse
    parsed_url = urlparse(page.url)
    path = parsed_url.path
    if not any(path.startswith(p) for p in VALID_CHECKOUT_PATHS):
        raise AssertionError(f"Unexpected checkout path: {page.url} (path: {path})")
    wait_for_spinner_to_clear(page)
    
    # Check for form elements
    page_content = page.content().lower()
    has_form = 'form' in page_content or 'input' in page_content
    
    if not has_form:
        raise AssertionError("No form elements found on checkout page")
    
    # Validate pricing - this is the critical check
    price = validate_pricing(page)
    if price <= 1.0:  # Price must be greater than $1
        error_msg = f"Pricing validation failed: Found price ${price:.2f} (must be > $1.00)"
        raise AssertionError(error_msg)

def cart_text(page) -> str:
    try:
        page.wait_for_selector(CART_CONTAINER_SELECTOR, timeout=5000)
        txt = page.locator(CART_CONTAINER_SELECTOR).inner_text()
    except Exception:
        txt = page.locator("body").inner_text()
    return " ".join(txt.split())

def assert_cart_correct(text: str):
    missing = [s.strip() for s in EXPECTED_CART_TEXT if s.strip() and s.strip() not in text]
    if missing:
        raise AssertionError(f"Cart text missing: {missing}")

def click_to_checkout(page):
    if page.locator(CTA_SELECTOR).count() > 0:
        page.locator(CTA_SELECTOR).first.click()
        return
    links = page.locator("a, button")
    n = links.count()
    for i in range(n):
        el = links.nth(i)
        try:
            href = el.get_attribute("href") or ""
            if "checkout" in href:
                el.click()
                return
        except Exception:
            continue
    raise AssertionError("No obvious checkout CTA found")

def check_flow(browser, start_url: str):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.set_default_timeout(PAGE_TIMEOUT)
    page.goto(start_url)
    wait_for_spinner_to_clear(page)
    _title = page.title()
    click_to_checkout(page)
    page.wait_for_load_state("domcontentloaded")
    ensure_checkout_ready(page)
    text = cart_text(page)
    assert_cart_correct(text)
    ctx.close()
    return {"start_url": start_url, "title": _title, "ok": True}

def main():
    results = []
    errors = []
    overall_status = True
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, args=["--no-sandbox"])
        for url in START_URLS:
            try:
                res = check_flow(browser, url)
                results.append(res)
                print(f"✅ {url} - Success")
            except Exception as e:
                ts = datetime.utcnow().isoformat()
                err = "".join(traceback.format_exception_only(type(e), e)).strip()
                error_info = {
                    "url": url,
                    "error": err,
                    "timestamp": ts
                }
                errors.append(error_info)
                overall_status = False
                print(f"❌ {url} - {err}", file=sys.stderr)
        browser.close()
    
    # Prepare final results
    final_results = {
        "ok": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "successful_checks": results,
        "errors": errors,
        "total_urls": len(START_URLS),
        "successful_count": len(results),
        "error_count": len(errors)
    }
    
    # Always send results to webhook
    send_results(final_results)
    
    # Print results locally
    print(json.dumps(final_results, indent=2))
    
    # Exit with error code if there were failures
    if not overall_status:
        sys.exit(2)

def run_continuously():
    """Run the checker continuously at specified intervals"""
    print(f"Starting BSU Checkout Monitor - running every {RUN_INTERVAL} minutes")
    
    while True:
        try:
            print(f"\n=== Running check at {datetime.utcnow().isoformat()} UTC ===")
            main()
            print(f"Check completed. Next run in {RUN_INTERVAL} minutes.")
        except KeyboardInterrupt:
            print("\nShutting down monitor...")
            break
        except Exception as e:
            print(f"Unexpected error in monitor loop: {e}", file=sys.stderr)
        
        # Wait for the specified interval
        time.sleep(RUN_INTERVAL * 60)

if __name__ == "__main__":
    # Check if we should run once or continuously
    run_once = os.getenv("RUN_ONCE", "false").lower() == "true"
    
    if run_once:
        main()
    else:
        run_continuously()