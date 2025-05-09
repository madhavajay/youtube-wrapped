import asyncio
import shutil
from pathlib import Path
import zipfile
import os
import time
from patched_playwright_engine import load_patched_playwright_engine
from scrapling.engines.toolbelt import Response, StatusText
from scrapling_utils import get_response_from_existing_page, create_wait_while_text_exists, wait_for_condition_and_continue, create_wait_while_text_not_exists

PROFILE_DIR = Path("./.browser-profile").resolve()
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
print("Using profile directory:", PROFILE_DIR)

DOWNLOAD_PATH = Path("./downloads").resolve()
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
print("Using download directory:", DOWNLOAD_PATH)

# Success function: Perform actions after successful sign-in
async def configure_takeout(response, page):
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

async def find_email_and_click_link(response, page):
    try:
        # Wait for the page to load and display emails
        await page.wait_for_selector('table[role="grid"]')

        # Find the email containing the specific link
        email_rows = await page.query_selector_all('tr:has-text("Your Google data is ready to download")')
        email_row = email_rows[0] if email_rows else None
        if email_row:
            await email_row.click()
            print("✅ Email with the specific link found and clicked.")
        else:
            print("⚠️ Email with the specific link not found.")

        # Wait for the email content to load
        await page.wait_for_selector('div[role="main"]')

        context = page.context
        # Setup listener for new page (i.e. new tab)
        new_page_promise = context.wait_for_event("page")

        # Find and click the link within the email
        link = await page.query_selector('a:has-text("Download your files")')
        if link:
            link_href = await link.get_attribute('href')
            await link.click()

        # Get the new page
        new_page = await new_page_promise

        # we might be asked to login again
        await create_wait_while_text_exists("Use your Google Account")(response, new_page)
        await create_wait_while_text_exists("Welcome")(response, new_page)

        # Wait for the download event on the new tab
        download = await new_page.wait_for_event("download")

        # Save the file to disk
        path = await download.path()
        if path:
            save_path = os.path.join(DOWNLOAD_PATH, download.suggested_filename)
            await download.save_as(save_path)
            print(f"✅ Download saved to: {save_path}")
        else:
            print("⚠️ No download path found.")

        if zipfile.is_zipfile(save_path):
            watch_history_path = await get_watch_history_path(save_path)
            if watch_history_path:
                destination_path = Path("./data/watch-history.html")
                destination_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
                shutil.copy2(watch_history_path, destination_path)
                print(f"✅ watch-history.html copied to: {destination_path}")
            else:
                print("⚠️ watch-history.html path not found, copy operation skipped.")


    except Exception as e:
        import traceback
        print(f"⚠️ Error: {e}\nTraceback: {traceback.format_exc()}")


async def automate_download_email_link():
    TARGET_URL = "https://gmail.com"
    PatchedEngine = load_patched_playwright_engine(PROFILE_DIR)
    engine = PatchedEngine(headless=False)

    response, page = await engine.async_interactive_fetch(TARGET_URL)
    await wait_for_condition_and_continue(
        response=response,
        page=page,
        url=TARGET_URL,
        wait_condition_fn=[
            create_wait_while_text_not_exists("Compose"),
        ],
        on_success_fn=find_email_and_click_link
    )

    await asyncio.sleep(3)
    await page.close()


async def unzip_takeout_file(zip_file_path):
    extract_to_path = DOWNLOAD_PATH / "extracted_takeout"
    
    if os.path.exists(extract_to_path):
        
        shutil.rmtree(extract_to_path)

    if not os.path.exists(extract_to_path):
        os.makedirs(extract_to_path)

    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to_path)
        print(f"✅ Files extracted to: {extract_to_path}")
    return extract_to_path if os.path.exists(extract_to_path) else None

def find_watch_history_file(extracted_path):
    """
    Searches for the file 'watch-history.html' several folders deep in the given extracted path.

    :param extracted_path: Path where the takeout files are extracted.
    :return: Full path to 'watch-history.html' if found, otherwise None.
    """
    for root, dirs, files in os.walk(extracted_path):
        if "watch-history.html" in files:
            watch_history_file = Path(root) / "watch-history.html"
            print(f"✅ Found watch-history.html at: {watch_history_file}")
            return watch_history_file
    print("⚠️ watch-history.html not found.")
    return None

async def get_watch_history_path(zip_file_path):
    try:
        extracted_path = await unzip_takeout_file(zip_file_path)
    except Exception as e:
        print(f"⚠️ Error during unzipping: {e}")
        return None

    try:
        watch_history_file = find_watch_history_file(extracted_path)
    except Exception as e:
        print(f"⚠️ Error finding watch-history.html: {e}")
        return None

    return watch_history_file


async def main():
    pass
    # await automate_takeout()
    # await automate_download_email_link()
    # a = await get_watch_history_path(DOWNLOAD_PATH / "takeout-20250509T020729Z-001.zip")
    # print(a)



if __name__ == "__main__":
    asyncio.run(main())


