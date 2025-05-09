import asyncio
from pathlib import Path
from patched_playwright_engine import load_patched_playwright_engine
from scrapling.engines.toolbelt import Response, StatusText
from scrapling_utils import get_response_from_existing_page, create_wait_while_text_exists, wait_for_condition_and_continue, create_wait_while_text_not_exists

PROFILE_DIR = Path("./.browser-profile").resolve()
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
print("Using profile directory:", PROFILE_DIR)

# Success function: Perform actions after successful sign-in
async def configure_takeout(response, page):
    new_response = await get_response_from_existing_page(
        page=page,
        history=response.history
    )

    try:
        # Click the "Deselect all" button
        deselect_all_button = await page.query_selector('text="Deselect all"')
        if deselect_all_button:
            await deselect_all_button.click()
            print("✅ 'Deselect all' button clicked.")
        else:
            print("⚠️ 'Deselect all' button not found.")

        # Scroll until the text "Youtube" is visible
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Attempt to click the checkbox for "YouTube and YouTube Music"
        youtube_checkbox = await page.query_selector('input[name="YouTube and YouTube Music"][type="checkbox"]')
        if youtube_checkbox:
            await youtube_checkbox.click()
            print("✅ 'YouTube and YouTube Music' checkbox clicked.")
        else:
            print("⚠️ 'YouTube and YouTube Music' checkbox not found.")

        # Attempt to click the button with the text "All YouTube data included"
        youtube_data_button = await page.query_selector('button:has-text("All YouTube data included")')
        if youtube_data_button:
            await youtube_data_button.click()
            print("✅ 'All YouTube data included' button clicked.")
        else:
            print("⚠️ 'All YouTube data included' button not found.")

        popup = await page.wait_for_selector('div:has-text("YouTube and YouTube Music content options")')

        if popup:
            # Step 3: Query *within that container only*
            deselect_buttons = await page.query_selector_all('button:has-text("Deselect all")')
            deselect_button = deselect_buttons[-1] if deselect_buttons else None

            if deselect_button:
                await deselect_button.click()
                print("✅ Deselect all clicked inside scoped container.")
            else:
                print("⚠️ Deselect button not found inside scoped container.")
        else:
            print("⚠️ Could not find popup for 'YouTube and YouTube Music' content options.")

        # Attempt to click the checkbox for "history"
        history_checkbox = await page.query_selector('input[name="history"][type="checkbox"]')
        if history_checkbox:
            await history_checkbox.click()
            print("✅ 'history' checkbox clicked.")
        else:
            print("⚠️ 'history' checkbox not found.")

        # await page.wait_for_selector('button:text-is("OK")', timeout=1000)
        # ok_button = await page.query_selector('button:text-is("OK")')
        # if ok_button:
        #     await ok_button.click()
        #     print("✅ 'OK' button clicked.")
        # else:
        #     print("⚠️ 'OK' button not found.")

        ok_spans = await page.query_selector_all('span:text-is("OK")')
        ok_span = ok_spans[-1] if ok_spans else None
        if ok_span:
            await ok_span.click()
            print("✅ 'OK' button clicked.")
        else:
            print("⚠️ 'OK' button not found.")

        # Attempt to click the "Next step" button using its aria-label
        next_step_button = await page.query_selector('button:has-text("Next step")')
        if next_step_button:
            await next_step_button.click()
            print("✅ 'Next step' button clicked.")
        else:
            print("⚠️ 'Next step' button not found.")


        create_export_button = await page.query_selector('button:has-text("Create export")')
        if create_export_button:
            await create_export_button.click()
            print("✅ 'Create export' button clicked.")
        else:
            print("⚠️ 'Create export' button not found.")

        # cancel_span = await page.query_selector('span:text-is("Cancel export")')
        # if cancel_span:
        #     print("✅ 'Cancel export' button found. Process is complete.")
        # else:
        #     print("⚠️ 'Cancel export' button not found.")

    except Exception as e:
        import traceback
        print(f"⚠️ Error: {e}\nTraceback: {traceback.format_exc()}")

async def automate_takeout():
    TARGET_URL = "https://takeout.google.com"
    PatchedEngine = load_patched_playwright_engine(PROFILE_DIR)
    engine = PatchedEngine(headless=False)

    response, page = await engine.async_interactive_fetch(TARGET_URL)
    await wait_for_condition_and_continue(
        response=response,
        page=page,
        url=TARGET_URL,
        wait_condition_fn=[
            create_wait_while_text_exists("Use your Google Account"),
            create_wait_while_text_exists("Welcome"),
            create_wait_while_text_not_exists("Manage exports"),
        ],
        on_success_fn=configure_takeout
    )

    await asyncio.sleep(3)
    await page.close()


async def main():
    await automate_takeout()

if __name__ == "__main__":
    asyncio.run(main())

