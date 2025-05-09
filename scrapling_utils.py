import asyncio
from pathlib import Path
from patched_playwright_engine import load_patched_playwright_engine
from scrapling.engines.toolbelt import Response, StatusText


async def wait_for_condition_and_continue(response, page, url, wait_condition_fn, on_success_fn, check_interval=1):
    print(f"🌐 Navigating to {url}")
    await page.goto(url)
    await page.wait_for_load_state("domcontentloaded")

    # Ensure wait_condition_fn is a list
    if not isinstance(wait_condition_fn, list):
        wait_condition_fn = [wait_condition_fn]

    print("⏳ Waiting for conditions...")
    for fn in wait_condition_fn:
        while True:
            try:
                if await fn(response, page):
                    print(f"✅ Condition {fn.__name__} met. Moving to next condition...")
                    break
            except Exception as e:
                print(f"⚠️ Condition check error: {e}")
            await asyncio.sleep(check_interval)

    print("✅ All conditions met. Executing action...")
    await on_success_fn(response, page)

from scrapling.engines.toolbelt import Response, StatusText

from scrapling.engines.toolbelt import Response

async def get_response_from_existing_page(page, history=None) -> Response:
    """
    Construct a basic Scrapling Response object from a Playwright Page.

    Parameters:
        page: The Playwright `page` object to extract content from.
        history: Optional list of prior responses for redirect history.

    Returns:
        A new `scrapling.engines.toolbelt.Response` object with basic metadata.
    """
    try:
        content = await page.content()
    except Exception as e:
        print(f"⚠️ Error getting page content: {e}")
        content = ""

    try:
        cookies = {
            cookie["name"]: cookie["value"]
            for cookie in await page.context.cookies()
        }
    except Exception as e:
        print(f"⚠️ Error getting cookies: {e}")
        cookies = {}

    # No reliable access to response headers/status here
    return Response(
        url=page.url,
        text=content,
        body=content.encode("utf-8"),
        status=200,
        reason="OK",
        encoding="utf-8",
        cookies=cookies,
        headers={},
        request_headers={},
        history=history or []
    )


# Condition function: Wait until the sign-in button appears
def create_wait_while_text_condition(text_to_find, should_exist=True):
    async def wait_while_text_condition(response, page):
        new_response = await get_response_from_existing_page(
            page=page,
            history=response.history
        )

        try:
            condition = "not visible" if should_exist else "visible"
            print(f"⏳ Waiting while '{text_to_find}' text is {condition}...")
            # Check if the specified text is visible or not based on should_exist
            text_found = new_response.find_by_text(text_to_find, partial=True)
            return text_found if should_exist else not text_found
        except Exception as e:
            print(f"⚠️ Error during wait for text '{text_to_find}': {e}")
            return not should_exist

    return wait_while_text_condition

def create_wait_while_text_exists(text_to_find):
    return create_wait_while_text_condition(text_to_find, should_exist=False)

def create_wait_while_text_not_exists(text_to_find):
    return create_wait_while_text_condition(text_to_find, should_exist=True)
