import pytest
import json
import datetime
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, call as mock_call

import pandas as pd
import isodate # For get_duration_seconds_from_metadata reference
import pytz # For robust timezone mocking
# Assuming requests is used by the module, for type hinting or direct patching
import requests 

# Add project root to sys.path to allow importing metadata
import sys
sys.path.append(str(Path(__file__).parent.parent))

from metadata import (
    load_metadata_cache,
    save_metadata_cache,
    extract_video_id,
    get_duration_seconds_from_metadata,
    fetch_video_metadata,
    fetch_and_save_youtube_category_mapping,
    process_rows,
    YoutubeDataPipelineState # Ensure this is imported if metadata.py uses it directly from utils via its own import
)

# --- Fixtures ---

@pytest.fixture
def app_data_dir(tmp_path):
    """Creates a temporary app_data directory with cache subdirectory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path

@pytest.fixture
def mock_utc_timezone(mocker):
    """Mocks tzlocal.get_localzone to always return UTC."""
    utc_tz = pytz.timezone("UTC")
    mocker.patch("metadata.tzlocal.get_localzone", return_value=utc_tz)
    return utc_tz

# --- Tests for Cache Functions ---

def test_load_metadata_cache_no_file(app_data_dir, mocker):
    mocker.patch("metadata.os.path.exists", return_value=False)
    cache = load_metadata_cache(app_data_dir)
    assert cache == {}
    metadata_file_path = app_data_dir / "cache" / "youtube_metadata.json"
    metadata.os.path.exists.assert_called_once_with(metadata_file_path)

def test_load_metadata_cache_file_exists(app_data_dir, mocker):
    expected_cache = {"video1": {"title": "Test Video"}}
    mock_json_data = json.dumps(expected_cache)
    
    mocker.patch("metadata.os.path.exists", return_value=True)
    m_open = mock_open(read_data=mock_json_data)
    mocker.patch("builtins.open", m_open)
    # json.load is called on the file handle returned by open, so direct mock of json.load can be tricky
    # For this test, if open provides the correct data, json.load inside the func should work.
    # If specific checks on json.load are needed, it can be mocked too.

    cache = load_metadata_cache(app_data_dir)
    
    metadata_file_path = app_data_dir / "cache" / "youtube_metadata.json"
    metadata.os.path.exists.assert_called_once_with(metadata_file_path)
    m_open.assert_called_once_with(metadata_file_path, "r", encoding="utf-8")
    assert cache == expected_cache

def test_save_metadata_cache(app_data_dir, mocker):
    cache_to_save = {"video2": {"title": "Another Video"}}
    expected_json_str = json.dumps(cache_to_save, indent=2, ensure_ascii=False)
    
    m_open = mock_open()
    mocker.patch("builtins.open", m_open)
    
    save_metadata_cache(cache_to_save, app_data_dir)
    
    metadata_file_path = app_data_dir / "cache" / "youtube_metadata.json"
    m_open.assert_called_once_with(metadata_file_path, "w", encoding="utf-8")
    m_open().write.assert_called_once_with(expected_json_str)

# --- Tests for extract_video_id ---
@pytest.mark.parametrize(
    "video_link, expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL...", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", None), 
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", None),
        ("invalid_link", None), ("", None), (None, None)
    ]
)
def test_extract_video_id(video_link, expected_id):
    assert extract_video_id(video_link) == expected_id

# --- Tests for get_duration_seconds_from_metadata ---
@pytest.mark.parametrize(
    "metadata_input, expected_seconds",
    [
        ({"contentDetails": {"duration": "PT1M30S"}}, 90),
        ({"contentDetails": {"duration": "PT1H"}}, 3600),
        ({"contentDetails": {"duration": "P1DT12H"}}, 129600),
        ({}, None), ({"contentDetails": {}}, None),
        ({"contentDetails": {"duration": "InvalidDuration"}}, None),
        (None, None), ({"contentDetails": {"duration": None}}, None),
    ]
)
def test_get_duration_seconds_from_metadata(metadata_input, expected_seconds, mocker):
    mocker.patch("builtins.print") # Suppress "Error parsing duration"
    assert get_duration_seconds_from_metadata(metadata_input) == expected_seconds

# --- Tests for fetch_video_metadata ---

@pytest.fixture
def mock_youtube_api_key():
    return "fake_api_key"

@pytest.fixture
def initial_cache_data():
    return {
        "cached_id1": {"id": "cached_id1", "snippet": {"title": "Cached Video 1"}},
    }

YOUTUBE_VIDEOS_API_URL = "https://www.googleapis.com/youtube/v3/videos"

def test_fetch_video_metadata_cache_hits(mock_youtube_api_key, initial_cache_data, mocker):
    video_ids_to_fetch = ["cached_id1"]
    cache_arg = initial_cache_data.copy()
    mock_requests_get = mocker.patch("metadata.requests.get")
    results = fetch_video_metadata(video_ids_to_fetch, mock_youtube_api_key, cache_arg)
    assert results[0]["id"] == "cached_id1"
    mock_requests_get.assert_not_called()

def test_fetch_video_metadata_cache_misses(mock_youtube_api_key, initial_cache_data, mocker):
    video_ids_to_fetch = ["cached_id1", "uncached_id1"]
    cache_arg = initial_cache_data.copy()
    mock_api_response = {"items": [{"id": "uncached_id1", "snippet": {"title": "Uncached Video 1"}}]}
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = mock_api_response
    mock_requests_get = mocker.patch("metadata.requests.get", return_value=mock_response)

    results = fetch_video_metadata(video_ids_to_fetch, mock_youtube_api_key, cache_arg)
    
    assert results[1]["id"] == "uncached_id1"
    mock_requests_get.assert_called_once()
    assert "uncached_id1" in cache_arg

def test_fetch_video_metadata_api_error(mock_youtube_api_key, mocker):
    video_ids_to_fetch = ["error_id1"]
    mock_response = MagicMock(status_code=500)
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("API Error")
    mocker.patch("metadata.requests.get", return_value=mock_response)
    mocker.patch("builtins.print")
    results = fetch_video_metadata(video_ids_to_fetch, mock_youtube_api_key, {})
    assert isinstance(results[0], str) and "API Error" in results[0]

def test_fetch_video_metadata_video_not_found(mock_youtube_api_key, mocker):
    video_ids_to_fetch = ["not_found_id"]
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"items": []} # No items for this ID
    mocker.patch("metadata.requests.get", return_value=mock_response)
    results = fetch_video_metadata(video_ids_to_fetch, mock_youtube_api_key, {})
    assert isinstance(results[0], str) and "not found or inaccessible" in results[0].lower()

def test_fetch_video_metadata_batching(mock_youtube_api_key, mocker):
    video_ids = [f"id_{i}" for i in range(55)] # 55 IDs to trigger batching
    def side_effect_batch_responses(url, params):
        resp = MagicMock(status_code=200)
        ids_in_batch = params["id"].split(',')
        resp.json.return_value = {"items": [{"id": vid} for vid in ids_in_batch]}
        return resp
    mock_get = mocker.patch("metadata.requests.get", side_effect=side_effect_batch_responses)
    fetch_video_metadata(video_ids, mock_youtube_api_key, {})
    assert mock_get.call_count == 2 # 50 + 5

# --- Tests for fetch_and_save_youtube_category_mapping ---
YOUTUBE_CATEGORIES_API_URL = "https://www.googleapis.com/youtube/v3/videoCategories"

@pytest.fixture
def region_cache_file(app_data_dir):
    return app_data_dir / "cache" / "youtube_category_test_region.json"

def test_fetch_category_mapping_loads_from_cache(mock_youtube_api_key, region_cache_file, mocker):
    expected_map = {"1": "Film"}
    mocker.patch("metadata.os.path.exists", return_value=True)
    mocker.patch("builtins.open", mock_open(read_data=json.dumps(expected_map)))
    mock_get = mocker.patch("metadata.requests.get")
    mapping = fetch_and_save_youtube_category_mapping(mock_youtube_api_key, region_cache_file)
    assert mapping == expected_map
    mock_get.assert_not_called()

def test_fetch_category_mapping_fetches_from_api(mock_youtube_api_key, region_cache_file, mocker):
    mocker.patch("metadata.os.path.exists", return_value=False)
    api_items = [{"id": "10", "snippet": {"title": "Music"}}]
    expected_map = {"10": "Music"}
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"items": api_items}
    mock_get = mocker.patch("metadata.requests.get", return_value=mock_resp)
    m_open = mock_open()
    mocker.patch("builtins.open", m_open)
    
    mapping = fetch_and_save_youtube_category_mapping(mock_youtube_api_key, region_cache_file, "GB")
    
    mock_get.assert_called_once_with(YOUTUBE_CATEGORIES_API_URL, params=pytest.approx({"part": "snippet", "regionCode": "GB", "key": mock_youtube_api_key}))
    m_open.assert_called_once_with(region_cache_file, "w", encoding="utf-8")
    assert json.loads(m_open().write.call_args[0][0]) == expected_map
    assert mapping == expected_map

# --- Tests for process_rows ---

@pytest.fixture
def sample_raw_df():
    # More diverse data for thorough testing
    return pd.DataFrame({
        "video_link": [
            "https://www.youtube.com/watch?v=vid1", # 2023
            "https://www.youtube.com/watch?v=vid2", # 2023
            "https://www.youtube.com/watch?v=vid3", # 2022
            "https://www.youtube.com/watch?v=vid4", # 2023, to be new
            "https://www.youtube.com/watch?v=vid5_invalid", # Invalid link
        ],
        "watch_time": [
            "2023-01-01T10:00:00Z", "2023-06-15T11:00:00Z",
            "2022-12-25T12:00:00Z", "2023-07-01T13:00:00Z",
            "2023-07-02T14:00:00Z",
        ]
    })

@pytest.fixture
def sample_existing_enriched_df():
    return pd.DataFrame({
        "video_link": ["https://www.youtube.com/watch?v=vid1", "https://www.youtube.com/watch?v=vid2"],
        "watch_time": ["2023-01-01T10:00:00Z", "2023-06-15T11:00:00Z"],
        "duration_seconds": [100, 200], "category_id": ["1", "2"], "category_name": ["Music", "Gaming"],
        "error": [None, None], "video_name": ["V1", "V2"], "channel_name": ["C1", "C2"], 
        "channel_link": ["L1", "L2"], "watch_time_dt": ["2023-01-01 10:00:00+00:00", "2023-06-15 11:00:00+00:00"]
    })

@pytest.fixture
def mock_pipeline_state(mocker):
    mock_state = MagicMock(spec=YoutubeDataPipelineState)
    mock_state.is_keep_running.return_value = True
    mocker.patch("metadata.YoutubeDataPipelineState", return_value=mock_state)
    return mock_state

@pytest.fixture
def mock_syft_client(mocker):
    return MagicMock(email="test@example.com")

@pytest.fixture(autouse=True) # Ensure this runs for all process_rows tests
def common_process_rows_mocks(mocker, mock_utc_timezone): # mock_utc_timezone ensures it's active
    mocker.patch("metadata.load_metadata_cache", return_value={})
    mocker.patch("metadata.save_metadata_cache")
    mocker.patch("metadata.fetch_and_save_youtube_category_mapping", return_value={"1": "Music", "2": "Gaming"})
    mocker.patch("metadata.add_dataset")
    mocker.patch("builtins.print") # Suppress tqdm, other prints
    # Default mock for fetch_video_metadata, can be overridden in specific tests
    mocker.patch("metadata.fetch_video_metadata", return_value=[]) 


def test_process_rows_initial_run(app_data_dir, sample_raw_df, mock_pipeline_state, mock_syft_client, mock_youtube_api_key, mocker):
    watch_history_path = str(app_data_dir / "raw.csv")
    enriched_data_path = str(app_data_dir / "enriched.csv")
    
    mocker.patch("metadata.pd.read_csv", return_value=sample_raw_df)
    mocker.patch("metadata.os.path.exists", return_value=False) # No existing enriched file
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv") # Patch where it's used

    # Specific mock for fetch_video_metadata for this test
    # vid1, vid2, vid3, vid4 are valid. vid5_invalid -> None ID
    mock_metadata_items = [
        {"id": "vid1", "snippet": {"title":"T1", "categoryId":"1", "channelTitle":"Ch1", "channelId":"cId1"}, "contentDetails": {"duration":"PT1M"}},
        {"id": "vid2", "snippet": {"title":"T2", "categoryId":"2", "channelTitle":"Ch2", "channelId":"cId2"}, "contentDetails": {"duration":"PT2M"}},
        {"id": "vid3", "snippet": {"title":"T3", "categoryId":"1", "channelTitle":"Ch3", "channelId":"cId3"}, "contentDetails": {"duration":"PT3M"}},
        {"id": "vid4", "snippet": {"title":"T4", "categoryId":"2", "channelTitle":"Ch4", "channelId":"cId4"}, "contentDetails": {"duration":"PT4M"}},
        # No entry for vid5_invalid as extract_video_id returns None
    ]
    # fetch_video_metadata is called with list of valid IDs.
    # The return is a list of results corresponding to *those valid IDs*.
    mocker.patch("metadata.fetch_video_metadata", return_value=mock_metadata_items)


    process_rows(mock_syft_client, mock_youtube_api_key, app_data_dir, watch_history_path, enriched_data_path, n=10)
    
    metadata.fetch_video_metadata.assert_called_once()
    # Check the list of video IDs passed to fetch_video_metadata
    # vid5_invalid's link results in None from extract_video_id, so it's not passed.
    assert metadata.fetch_video_metadata.call_args[0][0] == ["vid1", "vid2", "vid3", "vid4"]

    mock_to_csv.assert_called_once_with(enriched_data_path, index=False)
    written_df = mock_to_csv.call_args[0][0]
    
    assert len(written_df) == 5 # All rows from sample_raw_df processed
    assert written_df[written_df['video_link'].str.contains('vid1')]['duration_seconds'].iloc[0] == 60
    assert written_df[written_df['video_link'].str.contains('vid1')]['category_name'].iloc[0] == "Music"
    assert written_df[written_df['video_link'].str.contains('vid5_invalid')]['error'].iloc[0] is None # No ID -> No metadata -> No specific error from fetch

def test_process_rows_incremental_run(app_data_dir, sample_raw_df, sample_existing_enriched_df, mock_pipeline_state, mock_syft_client, mock_youtube_api_key, mocker):
    watch_history_path = str(app_data_dir / "raw.csv")
    enriched_data_path = str(app_data_dir / "enriched.csv")

    mocker.patch("metadata.pd.read_csv", side_effect=[sample_raw_df, sample_existing_enriched_df])
    mocker.patch("metadata.os.path.exists", return_value=True) # Enriched file exists
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv")

    # vid4 is new. vid5_invalid is also "new" but yields no ID.
    mock_metadata_item_vid4 = [{"id": "vid4", "snippet": {"title":"T4 New", "categoryId":"2", "channelTitle":"Ch4New", "channelId":"cId4New"}, "contentDetails": {"duration":"PT4M"}}]
    mocker.patch("metadata.fetch_video_metadata", return_value=mock_metadata_item_vid4)

    process_rows(mock_syft_client, mock_youtube_api_key, app_data_dir, watch_history_path, enriched_data_path, n=10)

    # fetch_video_metadata called only for new valid IDs: vid4
    metadata.fetch_video_metadata.assert_called_once_with(["vid4"], mock_youtube_api_key, mocker.ANY)
    
    written_df = mock_to_csv.call_args[0][0]
    # 2 new rows from raw_df (vid4, vid5_invalid) + 2 old rows from enriched_df
    assert len(written_df) == 2 + len(sample_existing_enriched_df) 
    assert written_df[written_df['video_link'].str.contains('vid4')]['video_name'].iloc[0] == "T4 New"
    # Check that old data is preserved
    assert written_df[written_df['video_link'].str.contains('vid1')]['video_name'].iloc[0] == "V1"


def test_process_rows_year_filter(app_data_dir, sample_raw_df, mock_pipeline_state, mock_syft_client, mock_youtube_api_key, mocker):
    watch_history_path = str(app_data_dir / "raw.csv")
    enriched_data_path = str(app_data_dir / "enriched.csv")
    
    mocker.patch("metadata.pd.read_csv", return_value=sample_raw_df)
    mocker.patch("metadata.os.path.exists", return_value=False)
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv")
    
    # Mock metadata only for vid3 (2022)
    mock_metadata_item_vid3 = [{"id": "vid3", "snippet": {"title":"T3 YearFiltered", "categoryId":"1"}, "contentDetails": {"duration":"PT3M"}}]
    mocker.patch("metadata.fetch_video_metadata", return_value=mock_metadata_item_vid3)

    process_rows(mock_syft_client, mock_youtube_api_key, app_data_dir, watch_history_path, enriched_data_path, year_filter=2022)
    
    # fetch_video_metadata should be called only for vid3 (from 2022)
    metadata.fetch_video_metadata.assert_called_once_with(["vid3"], mock_youtube_api_key, mocker.ANY)
    written_df = mock_to_csv.call_args[0][0]
    assert len(written_df) == 1 # Only vid3 row based on year_filter
    assert written_df['video_link'].iloc[0].endswith("vid3")
    assert written_df['video_name'].iloc[0] == "T3 YearFiltered"

def test_process_rows_n_parameter(app_data_dir, sample_raw_df, mock_pipeline_state, mock_syft_client, mock_youtube_api_key, mocker):
    watch_history_path = str(app_data_dir / "raw.csv")
    enriched_data_path = str(app_data_dir / "enriched.csv")

    mocker.patch("metadata.pd.read_csv", return_value=sample_raw_df)
    mocker.patch("metadata.os.path.exists", return_value=False)
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv")

    # Metadata for first 2 valid IDs: vid1, vid2
    mock_metadata_items_n2 = [
        {"id": "vid1", "snippet": {"title":"T1_n", "categoryId":"1"}, "contentDetails": {"duration":"PT1M"}},
        {"id": "vid2", "snippet": {"title":"T2_n", "categoryId":"2"}, "contentDetails": {"duration":"PT2M"}},
    ]
    mocker.patch("metadata.fetch_video_metadata", return_value=mock_metadata_items_n2)

    process_rows(mock_syft_client, mock_youtube_api_key, app_data_dir, watch_history_path, enriched_data_path, n=2)
    
    # sample_raw_df has 5 rows. extract_video_id results: vid1, vid2, vid3, vid4, None
    # So, links_to_process.head(n=2) will select rows for vid1, vid2.
    metadata.fetch_video_metadata.assert_called_once_with(["vid1", "vid2"], mock_youtube_api_key, mocker.ANY)
    written_df = mock_to_csv.call_args[0][0]
    assert len(written_df) == 2 # Only n=2 rows processed

def test_process_rows_stops_if_keep_running_false(app_data_dir, sample_raw_df, mock_pipeline_state, mock_syft_client, mock_youtube_api_key, mocker):
    mock_pipeline_state.is_keep_running.return_value = False # Stop immediately
    
    mock_read_csv = mocker.patch("metadata.pd.read_csv") # Should not be called if it stops early

    process_rows(mock_syft_client, mock_youtube_api_key, app_data_dir, "dummy_raw.csv", "dummy_enriched.csv")
    
    mock_read_csv.assert_not_called() # Check that processing didn't even start reading files

def test_process_rows_error_in_metadata_fetch(app_data_dir, sample_raw_df, mock_pipeline_state, mock_syft_client, mock_youtube_api_key, mocker):
    watch_history_path = str(app_data_dir / "raw.csv")
    enriched_data_path = str(app_data_dir / "enriched.csv")
    
    mocker.patch("metadata.pd.read_csv", return_value=sample_raw_df.head(1)) # Process only first row (vid1)
    mocker.patch("metadata.os.path.exists", return_value=False)
    mock_to_csv = mocker.patch("pandas.DataFrame.to_csv")
    
    # fetch_video_metadata returns an error string for vid1
    mocker.patch("metadata.fetch_video_metadata", return_value=["Error: API limit reached for vid1"])

    process_rows(mock_syft_client, mock_youtube_api_key, app_data_dir, watch_history_path, enriched_data_path, n=1)
    
    written_df = mock_to_csv.call_args[0][0]
    assert len(written_df) == 1
    assert written_df['error'].iloc[0] == "Error: API limit reached for vid1"
    assert pd.isna(written_df['duration_seconds'].iloc[0]) # Fields dependent on metadata should be None or default
    assert pd.isna(written_df['category_name'].iloc[0])

```
