import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, mock_open, call as mock_call
from pathlib import Path
import json # For API key config tests
import shutil # For mocking shutil.copy
import os # For mocking os.remove
import requests # For requests.exceptions.HTTPError
from fastapi import BackgroundTasks # For specing BackgroundTasks mock

# Import the FastAPI app instance
from app import app 

# --- Test Client Fixture ---

@pytest.fixture
def client(mock_pipeline_state_instance, mock_syft_client_and_app_globals):
    """
    Provides a TestClient for the FastAPI app.
    Relies on global mocks from conftest.py being active.
    """
    with TestClient(app) as test_client:
        yield test_client

# --- Tests for Endpoints (Verified and Refined) ---

def test_get_home_page_no_data(client, mock_pipeline_state_instance, mocker):
    mock_pipeline_state_instance.source_data_exists.return_value = False
    mock_pipeline_state_instance.enriched_data_exists.return_value = False
    mock_pipeline_state_instance.get_years.return_value = []
    mocker.patch("app.find_youtube_wrapped_html_files", return_value={})

    response = client.get("/")
    assert response.status_code == 200
    html_content = response.text.lower()
    assert "upload your youtube watch history" in html_content
    assert "no data processed yet" in html_content 
    assert "view your wrapped" not in html_content

def test_get_home_page_with_source_data(client, mock_pipeline_state_instance, mocker):
    mock_pipeline_state_instance.source_data_exists.return_value = True
    mock_pipeline_state_instance.enriched_data_exists.return_value = False
    mock_pipeline_state_instance.is_processing.return_value = False
    mocker.patch("app.find_youtube_wrapped_html_files", return_value={})

    response = client.get("/")
    assert response.status_code == 200
    html_content = response.text.lower()
    assert "process your data" in html_content 
    assert "data uploaded, ready to process" in html_content

def test_get_home_page_with_enriched_data(client, mock_pipeline_state_instance, mocker):
    mock_pipeline_state_instance.source_data_exists.return_value = True
    mock_pipeline_state_instance.enriched_data_exists.return_value = True
    mock_pipeline_state_instance.get_years.return_value = [2023, 2022]
    mock_wrapped_files = {2023: "path/to/2023.html", "all": "path/to/all.html"}
    mocker.patch("app.find_youtube_wrapped_html_files", return_value=mock_wrapped_files)

    response = client.get("/")
    assert response.status_code == 200
    html_content = response.text.lower()
    assert "view your youtube wrapped" in html_content
    assert "year 2023" in html_content
    assert "year all" in html_content

def test_get_home_page_processing_active(client, mock_pipeline_state_instance, mocker):
    mock_pipeline_state_instance.is_processing.return_value = True
    mocker.patch("app.find_youtube_wrapped_html_files", return_value={})

    response = client.get("/")
    assert response.status_code == 200
    html_content = response.text.lower()
    assert "processing in progress" in html_content
    assert "view status" in html_content

def test_post_upload(client, mocker):
    mock_process_upload = mocker.patch("app.process_upload", return_value=True)
    files = {"file-input": ("history.html", b"dummy content", "text/html")}
    response = client.post("/upload", files=files)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    mock_process_upload.assert_called_once()

def test_get_api_key_setup_no_existing_key(client, mocker, temp_app_data_dir):
    config_file = Path(app.CACHE_DIR) / "config.json" # app.CACHE_DIR is mocked
    if config_file.exists(): config_file.unlink()
    
    def mock_path_exists_side_effect(path_arg):
        if path_arg == config_file: return False
        # For other Path.exists calls, let's try to use original behavior if possible,
        # or a sensible default for tests. This is tricky with a global mock.
        # A more targeted patch on the specific Path instance in app.py's route would be better if this becomes an issue.
        return True # Default for other paths
    mocker.patch("pathlib.Path.exists", side_effect=mock_path_exists_side_effect)

    response = client.get("/api")
    assert response.status_code == 200
    assert 'value=""' in response.text.lower()
    assert any(call.args[0] == config_file for call in pathlib.Path.exists.call_args_list)

def test_get_api_key_setup_with_existing_key(client, mocker, temp_app_data_dir):
    existing_key = "fake_existing_key"
    config_file = Path(app.CACHE_DIR) / "config.json" # app.CACHE_DIR is mocked
    
    def mock_path_exists_side_effect(path_arg): return path_arg == config_file
    mocker.patch("pathlib.Path.exists", side_effect=mock_path_exists_side_effect)
    
    m_open = mock_open(read_data=json.dumps({"youtube-api-key": existing_key}))
    mocker.patch("builtins.open", m_open)

    response = client.get("/api")
    assert response.status_code == 200
    html_content = response.text.lower()
    
    pathlib.Path.exists.assert_any_call(config_file)
    m_open.assert_called_once_with(config_file, "r", encoding="utf-8")
    assert f'value="{existing_key}"' in html_content

def test_post_api_key_setup_valid_key(client, mocker, temp_app_data_dir):
    valid_api_key = "valid_key"
    mock_yt_response = MagicMock(status_code=200); mock_yt_response.json.return_value = {"items": ["data"]}
    mocker.patch("requests.get", return_value=mock_yt_response) 
    
    m_open = mock_open(); mocker.patch("builtins.open", m_open)
    mocker.patch("pathlib.Path.mkdir", return_value=None) # For save_config_to_file

    response = client.post("/api", data={"api_key": valid_api_key})
    assert response.status_code == 303; assert response.headers["location"] == "/"
    
    requests.get.assert_called_once()
    config_file = Path(app.CACHE_DIR) / "config.json" # app.CACHE_DIR is mocked
    m_open.assert_called_once_with(config_file, "w", encoding="utf-8")
    assert json.loads(m_open().write.call_args[0][0])["youtube-api-key"] == valid_api_key

def test_post_api_key_setup_invalid_key(client, mocker):
    mock_yt_response = MagicMock(status_code=400); mock_yt_response.json.return_value = {"error": {}}
    mock_yt_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Invalid key")
    mocker.patch("requests.get", return_value=mock_yt_response)
    m_open = mock_open(); mocker.patch("builtins.open", m_open)

    response = client.post("/api", data={"api_key": "invalid_key"})
    assert response.status_code == 400; assert "invalid" in response.json()["detail"].lower()
    m_open.assert_not_called()

def test_get_processing_status(client, mock_pipeline_state_instance):
    mock_pipeline_state_instance.is_processing.return_value = True
    mock_pipeline_state_instance.get_total_rows.return_value = 100
    mock_pipeline_state_instance.get_processed_rows.return_value = 50
    
    response = client.get("/processing-status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_processing"] is True; assert data["progress_percentage"] == 50.0

def test_post_process_original_starts_processing(client, mock_pipeline_state_instance, mocker, temp_app_data_dir):
    config_file = Path(app.CACHE_DIR) / "config.json"
    with open(config_file, "w") as f: json.dump({"youtube-api-key": "fake_valid_key"}, f)
    
    mock_process_rows_async_in_app = mocker.patch("app.process_rows_async") 
    
    def mock_path_exists_side_effect(path_arg): return path_arg == config_file
    mocker.patch("pathlib.Path.exists", side_effect=mock_path_exists_side_effect)
    mocker.patch("builtins.open", mock_open(read_data=json.dumps({"youtube-api-key": "fake_valid_key"})))

    response = client.post("/process", data={"year_filter": "all"})
    assert response.status_code == 303; assert response.headers["location"] == "/"
    mock_pipeline_state_instance.set_keep_running.assert_called_with(True)
    mock_pipeline_state_instance.set_processing.assert_called_with(True)
    mock_process_rows_async_in_app.assert_called_once()

# --- New/Updated Tests for Remaining Endpoints (Refined) ---

def test_post_start_processing_success(client, mock_pipeline_state_instance, mocker, temp_app_data_dir):
    config_file = Path(app.CACHE_DIR) / "config.json"
    with open(config_file, "w") as f: json.dump({"youtube-api-key": "fake_valid_key"}, f)
    mock_pipeline_state_instance.source_data_exists.return_value = True
    
    # Mock the BackgroundTasks instance that FastAPI will inject
    mock_bg_instance = MagicMock(spec=BackgroundTasks)
    # Patch the class BackgroundTasks where it's imported by app.py (or FastAPI itself if not re-imported)
    # Assuming app.py might do `from fastapi import BackgroundTasks` and it's used in route as `bt: BackgroundTasks`
    mocker.patch("fastapi.BackgroundTasks", return_value=mock_bg_instance) 
    # If app.py imports it like `from app.utils import BackgroundTasks` use `mocker.patch("app.utils.BackgroundTasks", ...)`
    # For this exercise, assuming direct import from fastapi in the route's module.
    
    mock_app_process_rows = mocker.patch("app.process_rows") # The actual task function

    response = client.post("/start-processing", data={"year_filter": "2023"})
    assert response.status_code == 200
    assert response.json() == {"message": "Processing started for year 2023"}
    
    mock_pipeline_state_instance.set_keep_running.assert_called_with(True)
    mock_pipeline_state_instance.set_processing.assert_called_with(True)
    
    mock_bg_instance.add_task.assert_called_once()
    called_task_func = mock_bg_instance.add_task.call_args[0][0]
    # called_task_args = mock_bg_instance.add_task.call_args[0][1:] # Positional args to process_rows
    called_task_kwargs = mock_bg_instance.add_task.call_args[1]   # Keyword args to process_rows

    assert called_task_func == mock_app_process_rows
    assert called_task_kwargs.get("year_filter") == "2023"
    # Assert other relevant args like client, api_key, paths are passed if necessary,
    # though some might be hard to assert if resolved inside the route from app state.

def test_post_start_processing_no_api_key(client, mock_pipeline_state_instance, temp_app_data_dir, mocker):
    config_file = Path(app.CACHE_DIR) / "config.json"; 
    if config_file.exists(): config_file.unlink()
    
    def mock_path_exists_side_effect(path_arg): return path_arg == config_file and False
    mocker.patch("pathlib.Path.exists", side_effect=mock_path_exists_side_effect)
    mocker.patch("builtins.open", mock_open(read_data=json.dumps({})))

    response = client.post("/start-processing", data={"year_filter": "2023"})
    assert response.status_code == 400 
    assert "api key not configured" in response.json()["detail"].lower()

def test_post_start_processing_no_source_data(client, mock_pipeline_state_instance, temp_app_data_dir, mocker):
    config_file = Path(app.CACHE_DIR) / "config.json"
    with open(config_file, "w") as f: json.dump({"youtube-api-key": "fake_valid_key"}, f)
    
    def mock_path_exists_side_effect(path_arg): return path_arg == config_file
    mocker.patch("pathlib.Path.exists", side_effect=mock_path_exists_side_effect)
    mocker.patch("builtins.open", mock_open(read_data=json.dumps({"youtube-api-key": "fake_valid_key"})))

    mock_pipeline_state_instance.source_data_exists.return_value = False

    response = client.post("/start-processing", data={"year_filter": "2023"})
    assert response.status_code == 400
    assert "source data not found" in response.json()["detail"].lower()

def test_post_stop_processing(client, mock_pipeline_state_instance, mocker):
    response = client.post("/stop-processing")
    assert response.status_code == 200
    assert response.json() == {"message": "Processing stopping..."}
    mock_pipeline_state_instance.set_keep_running.assert_called_with(False)
    mock_pipeline_state_instance.set_processing.assert_called_with(False)

def test_get_summarize(client, mock_pipeline_state_instance, mocker):
    year_to_summarize = 2023
    mock_create_share_image = mocker.patch("app.create_share_image") 
    mock_create_wrapped_page = mocker.patch("app.create_wrapped_page")
    mocker.patch("app.find_youtube_wrapped_html_files", return_value={
        year_to_summarize: f"dummy_path_to_wrapped_{year_to_summarize}.html"
    })

    response = client.get(f"/summarize?year={year_to_summarize}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert f"summary for youtube wrapped {year_to_summarize}" in response.text.lower()
    mock_create_wrapped_page.assert_called_once() 
    mock_create_share_image.assert_called_once()

def test_get_publish(client, mock_syft_client_and_app_globals, mocker):
    year_to_publish = 2023
    mock_client_instance = mock_syft_client_and_app_globals # Get the mocked syft client
    
    mocker.patch("app.create_share_image")
    mocker.patch("app.create_wrapped_page")

    private_html_path = Path(app.CACHE_DIR) / f"youtube-wrapped-{year_to_publish}.html"
    mocker.patch("app.find_youtube_wrapped_html_files", return_value={year_to_publish: str(private_html_path)})

    mock_shutil_copy = mocker.patch("shutil.copy")
    
    # Mock Path.exists for the private_html_path and the public directory
    # Mock Path.mkdir for creating the public directory
    expected_public_dir = mock_client_instance.datasite_path / "public" / "youtube-wrapped"
    
    def path_exists_side_effect(path_arg):
        if path_arg == private_html_path: return True # Private file exists
        if path_arg == expected_public_dir: return False # Public dir does not exist, needs creation
        return True # Default for other checks
    mocker.patch("pathlib.Path.exists", side_effect=path_exists_side_effect)
    mock_path_mkdir = mocker.patch("pathlib.Path.mkdir")

    response = client.get(f"/publish?year={year_to_publish}")
    assert response.status_code == 303; assert response.headers["location"] == "/"
    
    mock_path_mkdir.assert_any_call(expected_public_dir, parents=True, exist_ok=True)
    expected_dest_path = expected_public_dir / f"youtube-wrapped-{year_to_publish}.html"
    mock_shutil_copy.assert_called_once_with(str(private_html_path), expected_dest_path)

def test_get_unpublish(client, mock_syft_client_and_app_globals, mocker):
    year_to_unpublish = 2023
    mock_client_instance = mock_syft_client_and_app_globals
    
    public_file_target = mock_client_instance.datasite_path / "public" / "youtube-wrapped" / f"youtube-wrapped-{year_to_unpublish}.html"

    mock_public_file_path_obj = MagicMock(spec=Path)
    mock_public_file_path_obj.exists.return_value = True 
    
    def path_constructor_side_effect(path_arg):
        if path_arg == public_file_target:
            return mock_public_file_path_obj
        # Default mock for other Path() calls
        default_mock = MagicMock(spec=Path)
        # If Path() is called with other known paths, configure their exists() behavior here if needed
        default_mock.exists.return_value = False # Example default
        return default_mock
    mocker.patch("pathlib.Path", side_effect=path_constructor_side_effect) # Patch constructor
    
    response = client.get(f"/unpublish?year={year_to_unpublish}")
    assert response.status_code == 303; assert response.headers["location"] == "/"
    
    # Check that Path was constructed with public_file_target
    # This is tricky because Path() is called many times by FastAPI/Starlette too.
    # We rely on the side_effect to have returned our specific mock for that path.
    mock_public_file_path_obj.exists.assert_called_once()
    mock_public_file_path_obj.unlink.assert_called_once()


def test_get_delete_enriched(client, mocker, temp_app_data_dir):
    enriched_file = Path(app.DATA_DIR) / "watch-history-enriched.csv" # app.DATA_DIR is mocked

    mock_enriched_file_path_obj = MagicMock(spec=Path)
    mock_enriched_file_path_obj.exists.return_value = True
    
    def path_constructor_side_effect(path_arg):
        if path_arg == enriched_file:
            return mock_enriched_file_path_obj
        return MagicMock(spec=Path, exists=MagicMock(return_value=False)) # Default for other Path() calls
        
    mocker.patch("pathlib.Path", side_effect=path_constructor_side_effect)

    response = client.get("/delete-enriched")
    assert response.status_code == 303; assert response.headers["location"] == "/"
    
    mock_enriched_file_path_obj.exists.assert_called_once()
    mock_enriched_file_path_obj.unlink.assert_called_once()

def test_get_download_page(client):
    response = client.get("/download")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "download your youtube data" in response.text.lower()

def test_get_launch_takeout_agent(client, mocker):
    mock_automate_takeout = mocker.patch("app.helper.automate_takeout")
    response = client.get("/launch-takeout-agent")
    assert response.status_code == 303; assert response.headers["location"] == "/download"
    mock_automate_takeout.assert_called_once()

def test_get_launch_gmail_download_agent(client, mocker):
    mock_automate_email = mocker.patch("app.helper.automate_download_email_link")
    mocker.patch("app.process_upload", return_value=True) 

    response = client.get("/launch-gmail-download-agent")
    assert response.status_code == 303; assert response.headers["location"] == "/"
    mock_automate_email.assert_called_once()

```
