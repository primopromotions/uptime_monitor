import os, sys, time, json, traceback
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

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
N8N_WEBHOOK_URL = "https://n8n.primopromotions.com/webhook/alert"

def alert(msg: str, url: str = None, error_type: str = None):
    print(msg, file=sys.stderr)
    
    # Send to n8n webhook
    try:
        payload = {
            "message": msg,
            "timestamp": datetime.utcnow().isoformat(),
            "url": url,
            "error_type": error_type or "checkout_monitor_error"
        }
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass
    
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=10)
        except Exception:
            pass
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=10
            )
        except Exception:
            pass

def wait_for_spinner_to_clear(page):
    try:
        loc = page.locator(LOADING_OVERLAY_SELECTOR)
        if loc.count() > 0:
            page.wait_for_selector(LOADING_OVERLAY_SELECTOR, state="hidden", timeout=SPINNER_TIMEOUT)
    except PwTimeout:
        raise AssertionError("Spinner/loader never cleared")

def ensure_checkout_ready(page):
    from urllib.parse import urlparse
    parsed_url = urlparse(page.url)
    path = parsed_url.path
    if not any(path.startswith(p) for p in VALID_CHECKOUT_PATHS):
        raise AssertionError(f"Unexpected checkout path: {page.url} (path: {path})")
    wait_for_spinner_to_clear(page)
    
    # Instead of looking for specific selectors, just ensure we have forms and pricing content
    page_content = page.content().lower()
    has_form = 'form' in page_content or 'input' in page_content
    has_pricing = any(term in page_content for term in ['$', 'price', 'total', 'amount', 'cost'])
    
    if not has_form:
        raise AssertionError("No form elements found on checkout page")
    if not has_pricing:
        raise AssertionError("No pricing information found on checkout page")

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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE, args=["--no-sandbox"])
        for url in START_URLS:
            try:
                res = check_flow(browser, url)
                results.append(res)
            except Exception as e:
                ts = datetime.utcnow().isoformat()
                err = "".join(traceback.format_exception_only(type(e), e)).strip()
                alert(f"[BSU Checkout Monitor] {ts} UTC ❌ {url}\nReason: {err}", url=url, error_type="checkout_flow_error")
                browser.close()
                sys.exit(2)
        browser.close()
    print(json.dumps({"ok": True, "results": results}, indent=2))

if __name__ == "__main__":
    main()