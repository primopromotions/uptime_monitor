# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a BSU (Blood Sugar Ultra) checkout monitor - a web scraping tool that monitors e-commerce checkout flows for a health supplement product. The system uses Playwright to automate browser interactions and validates that the checkout process works correctly.

## Architecture

The application consists of two main components:

1. **checker.py** - Main monitoring script that:
   - Uses Playwright to navigate through predefined start URLs
   - Clicks through to checkout pages
   - Validates checkout readiness and cart content
   - Sends alerts via Slack/Telegram on failures

2. **Dockerfile** - Container configuration using Microsoft's Playwright Python image

## Core Configuration

The system is heavily driven by environment variables:

- `EXPECTED_CART_TEXT` - Comma-separated text that must appear in cart (default: "Subscribe & Save")
- `CTA_SELECTOR` - CSS selector for checkout buttons/links
- `LOADING_OVERLAY_SELECTOR` - Selector for loading spinners
- `CART_CONTAINER_SELECTOR` - Selector for cart content area
- `CHECKOUT_READY_SELECTOR` - Selector indicating checkout page is ready
- `PAGE_TIMEOUT_MS` / `SPINNER_TIMEOUT_MS` - Timeout configurations
- `SLACK_WEBHOOK_URL` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` - Alert configurations

## Running the Application

**Local execution:**
```bash
python checker.py
```

**Docker execution:**
```bash
docker build -t bsu-monitor .
docker run bsu-monitor
```

The script exits with code 2 on failures and sends alerts to configured notification channels.

## Key Flow Logic

1. Navigate to each URL in `START_URLS`
2. Wait for spinners to clear using `wait_for_spinner_to_clear()`
3. Find and click checkout CTA using `click_to_checkout()`
4. Validate checkout page readiness with `ensure_checkout_ready()`
5. Extract and validate cart text with `cart_text()` and `assert_cart_correct()`

## Testing and Validation

The system validates checkout flows by checking:
- URL paths match expected checkout paths (`/checkout`, `/checkout2`)
- Required selectors are present and loaded
- Cart contains expected text content
- No loading spinners are blocking the interface