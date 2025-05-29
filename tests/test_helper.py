import pytest
import zipfile
import os
import shutil
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, mock_open

# Add project root to sys.path to allow importing helper
import sys
sys.path.append(str(Path(__file__).parent.parent))

from helper import (
    unzip_takeout_file,
    find_watch_history_file,
    get_watch_history_path,
    configure_takeout, 
    automate_takeout,  
    create_find_email_and_click_link, 
    wait_for_condition_and_continue, 
    load_patched_playwright_engine 
)

# --- Fixtures ---

@pytest.fixture
def tmp_zip_file(tmp_path):
    zip_path = tmp_path / "takeout.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("dummy.txt", "dummy content")
    return zip_path

@pytest.fixture
def download_dir(tmp_path):
    return tmp_path / "downloads"

# --- Tests for Non-Playwright Functions (Verified from previous iteration) ---

def test_unzip_takeout_file_success(tmp_zip_file, download_dir, mocker):
    mock_zip_file_instance = MagicMock(spec=zipfile.ZipFile)
    # __enter__ and __exit__ need to be mocked for the 'with' statement
    mock_zip_context_manager = MagicMock()
    mock_zip_context_manager.__enter__.return_value = mock_zip_file_instance
    mock_zip_context_manager.__exit__.return_value = None
    mocker.patch("zipfile.ZipFile", return_value=mock_zip_context_manager)
    
    mocker.patch("helper.os.path.exists", return_value=False)
    mock_makedirs = mocker.patch("helper.os.makedirs")
    
    expected_extract_path = download_dir / tmp_zip_file.stem
    result_path = unzip_takeout_file(tmp_zip_file, download_dir)

    assert result_path == expected_extract_path
    zipfile.ZipFile.assert_called_once_with(tmp_zip_file, 'r')
    mock_zip_file_instance.extractall.assert_called_once_with(path=expected_extract_path)
    mock_makedirs.assert_called_once_with(expected_extract_path, exist_ok=True)


def test_unzip_takeout_file_existing_dir_removed(tmp_zip_file, download_dir, mocker):
    mock_zip_file_instance = MagicMock(spec=zipfile.ZipFile)
    mock_zip_context_manager = MagicMock()
    mock_zip_context_manager.__enter__.return_value = mock_zip_file_instance
    mock_zip_context_manager.__exit__.return_value = None
    mocker.patch("zipfile.ZipFile", return_value=mock_zip_context_manager)
        
    mocker.patch("helper.os.path.exists", return_value=True) 
    mock_rmtree = mocker.patch("helper.shutil.rmtree")
    mock_makedirs = mocker.patch("helper.os.makedirs") # Still called after rmtree
    
    expected_extract_path = download_dir / tmp_zip_file.stem
    unzip_takeout_file(tmp_zip_file, download_dir)

    mock_rmtree.assert_called_once_with(expected_extract_path)
    mock_makedirs.assert_called_once_with(expected_extract_path, exist_ok=True)


def test_unzip_takeout_file_zip_error(tmp_zip_file, download_dir, mocker):
    mocker.patch("zipfile.ZipFile", side_effect=zipfile.BadZipFile("Test error"))
    mock_print = mocker.patch("builtins.print")

    result_path = unzip_takeout_file(tmp_zip_file, download_dir)
    assert result_path is None
    mock_print.assert_any_call(f"Error unzipping file: Test error")


def test_find_watch_history_file_found_at_root(tmp_path):
    extracted_path = tmp_path / "takeout_extracted"
    extracted_path.mkdir()
    (extracted_path / "watch-history.html").touch()
    assert find_watch_history_file(extracted_path) == extracted_path / "watch-history.html"

def test_find_watch_history_file_found_nested(tmp_path):
    extracted_path = tmp_path / "takeout_extracted"
    nested_dir = extracted_path / "Takeout" / "YouTube and YouTube Music" / "History"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "watch-history.html").touch()
    assert find_watch_history_file(extracted_path) == nested_dir / "watch-history.html"

def test_find_watch_history_file_not_found(tmp_path, mocker):
    extracted_path = tmp_path / "takeout_extracted"
    extracted_path.mkdir()
    # Mock os.walk to simulate not finding the file
    mocker.patch("helper.os.walk", return_value=[(str(extracted_path), [], ["other.txt"])])
    assert find_watch_history_file(extracted_path) is None


def test_get_watch_history_path_success(tmp_zip_file, download_dir, mocker):
    mocker.patch("helper.zipfile.is_zipfile", return_value=True)
    mock_unzip_path = download_dir / "takeout_extracted_content"
    mocker.patch("helper.unzip_takeout_file", return_value=mock_unzip_path)
    expected_history_file = mock_unzip_path / "watch-history.html"
    mocker.patch("helper.find_watch_history_file", return_value=expected_history_file)

    assert get_watch_history_path(tmp_zip_file, download_dir) == expected_history_file

def test_get_watch_history_path_not_a_zip(tmp_zip_file, download_dir, mocker):
    mocker.patch("helper.zipfile.is_zipfile", return_value=False)
    mock_print = mocker.patch("builtins.print")
    assert get_watch_history_path(tmp_zip_file, download_dir) is None
    mock_print.assert_any_call(f"{tmp_zip_file} is not a valid zip file.")

def test_get_watch_history_path_unzip_fails(tmp_zip_file, download_dir, mocker):
    mocker.patch("helper.zipfile.is_zipfile", return_value=True)
    mocker.patch("helper.unzip_takeout_file", return_value=None)
    mock_print = mocker.patch("builtins.print")
    assert get_watch_history_path(tmp_zip_file, download_dir) is None
    mock_print.assert_any_call(f"Failed to extract Takeout file from {tmp_zip_file}")

def test_get_watch_history_path_find_fails(tmp_zip_file, download_dir, mocker):
    mocker.patch("helper.zipfile.is_zipfile", return_value=True)
    mock_unzip_path = download_dir / "takeout_extracted_content"
    mocker.patch("helper.unzip_takeout_file", return_value=mock_unzip_path)
    mocker.patch("helper.find_watch_history_file", return_value=None)
    mock_print = mocker.patch("builtins.print")
    assert get_watch_history_path(tmp_zip_file, download_dir) is None
    mock_print.assert_any_call(f"watch-history.html not found in {mock_unzip_path}")

# --- Tests for Playwright Functions (Refined) ---

@pytest.mark.asyncio
async def test_configure_takeout(mocker):
    mock_response = MagicMock() 
    mock_page = AsyncMock(spec=["query_selector", "evaluate", "wait_for_selector", "click"]) 

    mock_deselect_all_btn = AsyncMock(spec=["click"])
    mock_show_more_btn = AsyncMock(spec=["click"])
    mock_youtube_label = AsyncMock(spec=["query_selector", "click"]) # Label can be clicked too
    mock_youtube_checkbox = AsyncMock(spec=["is_checked", "click"])
    mock_next_btn = AsyncMock(spec=["click"])
    mock_create_export_btn = AsyncMock(spec=["click"])

    # Simulate the sequence of element discovery and interaction
    # query_selector used for "Deselect All" / "Select All" button
    # and for "Next" and "Create Export" buttons
    mock_page.query_selector.side_effect = [
        mock_deselect_all_btn,      # For "Deselect all" / "Select all"
        mock_show_more_btn,         # For "Show more products" button
        mock_youtube_label,         # For "YouTube" label (alternative to wait_for_selector)
        mock_next_btn,              # For "Next step"
        mock_create_export_btn,     # For "Create export"
        None # Default for any other unexpected calls
    ]
    
    # page.evaluate for checking button text
    mock_page.evaluate.return_value = "Deselect all" # Assume "Deselect all" is found and clicked

    # wait_for_selector for YouTube label (can also be mocked if query_selector is used for it)
    # If we use query_selector for YouTube label as above, wait_for_selector might not be called for it.
    # For robustness, let's assume it might be called.
    mock_page.wait_for_selector.return_value = mock_youtube_label

    mock_youtube_label.query_selector.return_value = mock_youtube_checkbox
    mock_youtube_checkbox.is_checked.return_value = False # Simulate it needs checking

    await configure_takeout(mock_response, mock_page)

    mock_deselect_all_btn.click.assert_called_once()
    mock_show_more_btn.click.assert_called_once()
    
    # Verify YouTube checkbox interaction
    # wait_for_selector might be called before query_selector for the label
    mock_page.wait_for_selector.assert_any_call("label[data-value='YOUTUBE']", timeout=5000)
    # Or, if query_selector for label is used directly:
    # mock_page.query_selector.assert_any_call("label[data-value='YOUTUBE']")

    mock_youtube_label.query_selector.assert_called_once_with("input[type='checkbox']")
    mock_youtube_checkbox.is_checked.assert_called_once()
    mock_youtube_checkbox.click.assert_called_once() # Clicked because is_checked was False

    mock_next_btn.click.assert_called_once()
    mock_create_export_btn.click.assert_called_once()

@pytest.mark.asyncio
async def test_automate_takeout(tmp_path, mocker):
    cache_dir = tmp_path / "helper_cache"; cache_dir.mkdir()

    mock_engine = MagicMock()
    mock_response_obj = MagicMock()
    mock_page_obj = AsyncMock(spec=["context"]) # Ensure context attribute is mockable
    mock_page_obj.context.close = AsyncMock() # Mock the close method on the context
    mock_engine.async_interactive_fetch.return_value = (mock_response_obj, mock_page_obj)
    
    mocker.patch("helper.load_patched_playwright_engine", return_value=mock_engine)
    mock_configure = mocker.patch("helper.configure_takeout", new_callable=AsyncMock)
    # wait_for_condition_and_continue returns None, so AsyncMock is fine
    mock_wait_for_condition = mocker.patch("helper.wait_for_condition_and_continue", new_callable=AsyncMock) 
    mock_asyncio_sleep = mocker.patch("asyncio.sleep", new_callable=AsyncMock)

    await automate_takeout(cache_dir)

    helper.load_patched_playwright_engine.assert_called_once()
    mock_engine.async_interactive_fetch.assert_called_once()
    mock_configure.assert_called_once_with(mock_response_obj, mock_page_obj)
    assert mock_wait_for_condition.call_count >= 1 # Called for multiple conditions
    mock_page_obj.context.close.assert_called_once()
    assert mock_asyncio_sleep.call_count >=1 # Called at least once

@pytest.mark.asyncio
async def test_create_find_email_and_click_link_inner_function_refined(tmp_path, mocker):
    download_path = tmp_path / "email_downloads"; download_path.mkdir()
    
    inner_find_func = create_find_email_and_click_link(download_path)

    mock_response = MagicMock()
    mock_page = AsyncMock(spec=["query_selector_all", "query_selector", "wait_for_selector", "context", "click"])
    mock_page.context.wait_for_event = AsyncMock() # Mock for "page" event

    mock_email_row = AsyncMock(spec=["evaluate", "click"])
    mock_page.query_selector_all.return_value = [mock_email_row]
    mock_email_row.evaluate.return_value = "Your takeout data is ready" 
    
    mock_download_link_in_email = AsyncMock(spec=["get_attribute", "click"])
    # This query_selector is for the download link *within the email view*
    mock_page.query_selector.return_value = mock_download_link_in_email
    mock_download_link_in_email.get_attribute.return_value = "http://example.com/download_link"

    # Mocking the new page and download event sequence
    mock_new_page_after_click = AsyncMock(spec=["wait_for_event"]) # Page opened by clicking download link
    mock_page.context.wait_for_event.return_value = mock_new_page_after_click # "page" event returns new page

    mock_download_event = AsyncMock(spec=["path", "save_as"])
    mock_new_page_after_click.wait_for_event.return_value = mock_download_event # "download" event on new page
    
    # Create a dummy file for download_event.path() to return, so save_as can be "called" on it
    # This path is what Playwright internally uses before save_as.
    temp_downloaded_zip_path = tmp_path / "temp_downloaded_file.zip"
    temp_downloaded_zip_path.touch()
    mock_download_event.path.return_value = str(temp_downloaded_zip_path) # Must be a string

    expected_saved_zip_path = download_path / "takeout.zip" # Where save_as will place it

    mocker.patch("helper.zipfile.is_zipfile", return_value=True)
    expected_history_file_in_zip = tmp_path / "final_history.html" # Mocked return from get_watch_history_path
    mocker.patch("helper.get_watch_history_path", return_value=expected_history_file_in_zip)
    mock_shutil_copy = mocker.patch("helper.shutil.copy2")
    mocker.patch("builtins.print")

    result_path = await inner_find_func(mock_response, mock_page)

    # Assertions
    mock_page.wait_for_selector.assert_any_call("tr.zA.yO", timeout=60000)
    mock_email_row.click.assert_called_once()
    mock_download_link_in_email.click.assert_called_once() # Click on link in email
    
    # Check "page" event was awaited, then "download" event on the new page
    mock_page.context.wait_for_event.assert_called_once_with("page", timeout=60000)
    mock_new_page_after_click.wait_for_event.assert_called_once_with("download", timeout=300000)
    
    mock_download_event.save_as.assert_called_once_with(expected_saved_zip_path)
    helper.get_watch_history_path.assert_called_once_with(expected_saved_zip_path, download_path)
    mock_shutil_copy.assert_called_once_with(expected_history_file_in_zip, download_path / "watch-history.html")
    assert result_path == download_path / "watch-history.html"

```
