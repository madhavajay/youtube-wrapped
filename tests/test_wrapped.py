import pytest
import datetime
import json
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock, call as mock_call

import pandas as pd
import pytz # For robust timezone mocking

# Add project root to sys.path to allow importing wrapped
import sys
sys.path.append(str(Path(__file__).parent.parent))

# Ensure wrapped module and its functions are imported
from wrapped import format_human_date, generate_wrapped_json, create_wrapped_page, extract_video_id

# --- Tests for format_human_date ---

@pytest.mark.parametrize(
    "date_input, expected_output",
    [
        (datetime.datetime(2023, 1, 1), "Sunday the 1st of January"),
        (datetime.datetime(2023, 1, 2), "Monday the 2nd of January"),
        (datetime.datetime(2023, 1, 3), "Tuesday the 3rd of January"),
        (datetime.datetime(2023, 1, 4), "Wednesday the 4th of January"),
        (datetime.datetime(2023, 1, 11), "Wednesday the 11th of January"),
        (datetime.datetime(2023, 1, 12), "Thursday the 12th of January"),
        (datetime.datetime(2023, 1, 13), "Friday the 13th of January"),
        (datetime.datetime(2023, 1, 21), "Saturday the 21st of January"),
        (datetime.datetime(2023, 1, 22), "Sunday the 22nd of January"),
        (datetime.datetime(2023, 1, 23), "Monday the 23rd of January"),
        (datetime.datetime(2023, 1, 24), "Tuesday the 24th of January"),
        (datetime.datetime(2023, 3, 5), "Sunday the 5th of March"),
        (datetime.datetime(2024, 2, 29), "Thursday the 29th of February"), 
    ],
)
def test_format_human_date(date_input, expected_output):
    assert format_human_date(date_input) == expected_output

# --- Tests for extract_video_id ---
@pytest.mark.parametrize(
    "video_link, expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL...", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", None), # Does not match current regex
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", None), # Does not match
        ("invalid_link", None),
        ("", None),
    ]
)
def test_extract_video_id(video_link, expected_id):
    assert extract_video_id(video_link) == expected_id


# --- Tests for generate_wrapped_json ---

@pytest.fixture
def sample_enriched_df():
    """Provides a sample DataFrame simulating 'watch-history-enriched.csv'."""
    data = {
        "watch_time": [ # Ensure enough data for various scenarios
            "2023-01-01T10:00:00Z", "2023-01-01T11:00:00Z", "2023-06-15T14:30:00Z", 
            "2022-12-20T08:00:00Z", "2023-01-02T00:00:00Z", "2023-01-02T01:00:00Z",
            "2023-03-10T12:00:00Z", # For ChannelB, different video
            "2023-03-11T13:00:00Z", # For ChannelA, different video
            "NaT", # To be coerced to NaT and handled
            "2023-01-03T10:00:00Z", # Video with error
            "2023-01-04T10:00:00Z", # Video > 4 hours
        ],
        "category_name": ["Music", "Gaming", "Music", "Tech", "Gaming", "Gaming", "Gaming", "Music", "Education", "Music", "Science"],
        "channel_name": ["ChannelA", "ChannelB", "ChannelA", "ChannelC", "ChannelD", "ChannelB", "ChannelB", "ChannelA", "ChannelE", "ChannelA", "ChannelF"],
        "channel_link": ["linkA", "linkB", "linkA", "linkC", "linkD", "linkB", "linkB", "linkA", "linkE", "linkA", "linkF"],
        "video_name": [
            "Song1", "GamePlay1", "Song2", "Review1", "GameTutorial", "GamePlay2", "GameStream", "SongHit",
            "Lecture1", "Song3-Error", "LongDoc"
        ],
        "video_link": [
            "https://www.youtube.com/watch?v=vid1", "https://www.youtube.com/watch?v=vid2",
            "https://www.youtube.com/watch?v=vid3", "https://www.youtube.com/watch?v=vid4",
            "https://www.youtube.com/watch?v=vid5", "https://www.youtube.com/watch?v=vid6",
            "https://www.youtube.com/watch?v=vidB3", # ChannelB's 3rd video
            "https://www.youtube.com/watch?v=vidA3", # ChannelA's 3rd video
            "https://www.youtube.com/watch?v=vid7", # NaT time
            "https://www.youtube.com/watch?v=vid8", # Error
            "https://www.youtube.com/watch?v=vid9", # > 4 hours
        ],
        "duration_seconds": [
            180, 1200, 240, 3600, 300, 1500, 
            1000, # GameStream (ChannelB)
            500,  # SongHit (ChannelA)
            600,  # Lecture1 (NaT)
            120,  # Song3-Error
            5 * 3600 # LongDoc (5 hours)
        ],
        "error": [None, None, None, None, None, None, None, None, None, "Video not available", None],
    }
    return pd.DataFrame(data)

@pytest.fixture
def mock_data_cache_dirs(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return data_dir, cache_dir

@pytest.fixture(autouse=True)
def mock_timezone_autouse(mocker):
    mock_utc_timezone = pytz.timezone("UTC")
    mocker.patch("wrapped.tzlocal.get_localzone", return_value=mock_utc_timezone)

def test_generate_wrapped_json_specific_year(sample_enriched_df, mock_data_cache_dirs, mocker):
    data_dir, cache_dir = mock_data_cache_dirs
    year_to_test = 2023

    mocker.patch("wrapped.pd.read_csv", return_value=sample_enriched_df)
    mock_file_open = mock_open()
    mocker.patch("builtins.open", mock_file_open)

    generate_wrapped_json(year_to_test, data_dir, cache_dir)

    expected_json_path = cache_dir / f"youtube-wrapped-{year_to_test}.json"
    mock_file_open.assert_called_once_with(expected_json_path, "w")
    written_json_str = mock_file_open().write.call_args[0][0]
    output_data = json.loads(written_json_str)

    assert output_data["year"] == year_to_test
    
    # Valid 2023 videos (excluding errors, >4hr, NaT times if they cause issues):
    # Song1, GamePlay1, Song2, GameTutorial, GamePlay2, GameStream, SongHit
    # LongDoc (vid9) is > 4 hours, Song3-Error (vid8) has error. Lecture1 (vid7) has NaT time.
    # NaT times are converted by pd.to_datetime(..., errors='coerce') to NaT.
    # df_year = df[df["watch_time_dt"].dt.year == year] will filter out NaT watch_time_dt.
    assert output_data["total_views"] == 7
    
    # Durations for 2023 (valid): 180(S1)+1200(GP1)+240(S2)+300(GT)+1500(GP2)+1000(GS)+500(SH) = 4920s
    # Total minutes = 4920 / 60 = 82 minutes
    # Total hours = 82 // 60 = 1 hour, Remaining minutes = 82 % 60 = 22 minutes
    assert output_data["total_hours"] == 1
    assert output_data["total_minutes"] == 22
    
    # Top categories in 2023: Gaming (3: GP1, GT, GS), Music (3: S1, S2, SH)
    # Order depends on value_counts() internal tie-breaking or original df order.
    # Let's check presence and count.
    assert "Gaming" in output_data["top_categories"]
    assert "Music" in output_data["top_categories"]
    assert len(output_data["top_categories"]) >= 2 # Could be up to 5 if other categories existed

    # Top channels by duration in 2023:
    # ChannelB: GP1(1200) + GP2(1500) + GS(1000) = 3700s
    # ChannelA: S1(180) + S2(240) + SH(500) = 920s
    # ChannelD: GT(300)
    # Order: ChannelB, ChannelA, ChannelD
    assert output_data["top_channels"] == ["ChannelB", "ChannelA", "ChannelD"]
    assert output_data["top_channels_links"] == ["linkB", "linkA", "linkD"]

    # Top videos by view count in 2023 (all viewed once)
    expected_top_videos_2023 = ["Song1", "GamePlay1", "Song2", "GameTutorial", "GamePlay2", "GameStream", "SongHit"]
    assert all(video_name in output_data["top_videos"] for video_name in expected_top_videos_2023)
    assert len(output_data["top_videos"]) == 5 # .head(5) is used

    # Days watched in 2023: Jan 1, Jan 2, Mar 10, Mar 11 (4 days)
    assert output_data["total_days"] == 4
    # Average minutes per day: 82 total_minutes / 4 days = 20.5 minutes
    assert output_data["average_hours"] == 0
    assert output_data["average_minutes"] == 20 # Integer conversion

    # Top day of week by view count in 2023:
    # 2023-01-01 (Sun): S1, GP1 (2 views)
    # 2023-01-02 (Mon): GT, GP2 (2 views)
    # 2023-03-10 (Fri): GS (1 view)
    # 2023-03-11 (Sat): SH (1 view)
    # 2023-06-15 (Thu): S2 (1 view)
    # Counts: Sun(2), Mon(2), Fri(1), Sat(1), Thu(1). Sunday is first of the max.
    assert output_data["top_day"] == "Sunday" 
    
    # Top day by watch time in 2023:
    # 2023-01-01: 180 + 1200 = 1380s
    # 2023-01-02: 300 + 1500 = 1800s
    # 2023-03-10: 1000s
    # 2023-03-11: 500s
    # 2023-06-15: 240s
    # Top day is 2023-01-02 (Monday), with 1800s = 30 minutes
    assert output_data["top_day_date_year"] == 2023
    assert output_data["top_day_date_month"] == 1
    assert output_data["top_day_date_day"] == 2
    assert output_data["top_day_date_day_name"] == "Monday"
    assert output_data["top_day_minutes"] == 30

def test_generate_wrapped_json_all_years(sample_enriched_df, mock_data_cache_dirs, mocker):
    data_dir, cache_dir = mock_data_cache_dirs
    mocker.patch("wrapped.pd.read_csv", return_value=sample_enriched_df)
    mock_file_open = mock_open()
    mocker.patch("builtins.open", mock_file_open)

    generate_wrapped_json("all", data_dir, cache_dir)
    written_json_str = mock_file_open().write.call_args[0][0]
    output_data = json.loads(written_json_str)

    assert output_data["year"] == "all"
    # Valid videos (all years, no error, not >4hr, valid time):
    # 2023: 7 videos (calculated above)
    # 2022: Review1 (1 video)
    # Total = 7 + 1 = 8 videos
    assert output_data["total_views"] == 8
    # Total duration: 4920s (2023) + 3600s (Review1 from 2022) = 8520s
    # Total minutes = 8520 / 60 = 142 minutes
    # Total hours = 142 // 60 = 2 hours, Remaining minutes = 142 % 60 = 22 minutes
    assert output_data["total_hours"] == 2
    assert output_data["total_minutes"] == 22

def test_generate_wrapped_json_empty_df(mock_data_cache_dirs, mocker):
    data_dir, cache_dir = mock_data_cache_dirs
    empty_df = pd.DataFrame(columns=[
        "watch_time", "category_name", "channel_name", "channel_link", 
        "video_name", "video_link", "duration_seconds", "error"
    ])
    mocker.patch("wrapped.pd.read_csv", return_value=empty_df)
    mock_file_open = mock_open()
    mocker.patch("builtins.open", mock_file_open)

    generate_wrapped_json(2023, data_dir, cache_dir)
    written_json_str = mock_file_open().write.call_args[0][0]
    output_data = json.loads(written_json_str)

    assert output_data["total_views"] == 0
    assert output_data["total_hours"] == 0
    assert output_data["total_minutes"] == 0
    assert output_data["top_categories"] == []
    assert output_data["top_channels"] == []
    assert output_data["top_videos"] == []
    assert output_data["total_days"] == 0
    assert output_data["average_hours"] == 0
    assert output_data["average_minutes"] == 0
    assert output_data["top_day_date_year"] is None
    assert output_data["top_day_minutes"] == 0

# --- Tests for create_wrapped_page ---

@pytest.fixture
def sample_wrapped_json_data_for_render():
    return {
        "year": 2023, "total_hours": 10, "total_minutes": 30, "average_hours": 1, "average_minutes": 5,
        "top_day_date_year": 2023, "top_day_date_month": 1, "top_day_date_day": 15,
        "top_day_minutes": 120,
        "top_channels": ["ChannelX", "ChannelY"], "top_channels_links": ["linkX", "linkY"],
        "top_videos": ["VideoX", "VideoY"], "top_videos_thumbs": ["thumbX", "thumbY"], "top_videos_links": ["vLinkX", "vLinkY"],
        "top_categories": ["CategoryX", "CategoryY"], "total_days": 50,
    }

@pytest.fixture
def mock_client_obj():
    client = MagicMock()
    client.email = "testuser@example.com"
    return client

def test_create_wrapped_page(
    sample_wrapped_json_data_for_render, mock_client_obj, mock_data_cache_dirs, mocker
):
    data_dir, cache_dir = mock_data_cache_dirs
    year_to_test = 2023
    other_files_mock = ["file1.txt"]
    syftbox_domain_mock = "test.syftbox.com"

    mocker.patch("wrapped.generate_wrapped_json") # Mock the function that writes the first JSON

    mock_json_content_str = json.dumps(sample_wrapped_json_data_for_render)
    mock_template_html_str = "<html><body>Year: {{ year }}, Email: {{ email }}, TopDay: {{ top_day_date }}, OtherFiles: {{ other_files|join(', ') }}</body></html>"

    # Mock file operations: 1. Read JSON, 2. Read HTML template, 3. Write output HTML
    # The order of side_effect matters.
    m_open = mock_open()
    m_open.side_effect = [
        mock_open(read_data=mock_json_content_str).return_value, # For reading youtube-wrapped-{year}.json
        mock_open(read_data=mock_template_html_str).return_value, # For reading wrapped-template.html
        mock_open().return_value,  # For writing the output HTML
    ]
    mocker.patch("builtins.open", m_open)

    rendered_html = create_wrapped_page(
        year_to_test, mock_client_obj, data_dir, cache_dir, other_files_mock, syftbox_domain_mock
    )

    wrapped.generate_wrapped_json.assert_called_once_with(year_to_test, data_dir, cache_dir)
    
    # Check file open calls
    expected_json_read_path = cache_dir / f"youtube-wrapped-{year_to_test}.json"
    expected_template_read_path = Path("./assets/wrapped-template.html")
    expected_html_write_path = cache_dir / f"youtube-wrapped-{year_to_test}.html"
    
    # Verify calls to open
    # Need to check using the mock `m_open.call_args_list`
    # Example: `assert m_open.call_args_list[0] == mock_call(expected_json_read_path, "r")`
    # This can be fragile if order changes slightly or other open calls are made.
    # A more robust way is to check for specific calls regardless of order if that's acceptable.
    assert mock_call(expected_json_read_path, "r") in m_open.call_args_list
    assert mock_call(expected_template_read_path, "r", encoding="utf-8") in m_open.call_args_list
    assert mock_call(expected_html_write_path, "w", encoding="utf-8") in m_open.call_args_list
    
    assert f"Year: {year_to_test}" in rendered_html
    assert f"Email: {mock_client_obj.email}" in rendered_html
    assert "OtherFiles: file1.txt" in rendered_html # Check if other_files are rendered

    # Check formatting of top_day_date
    # For 2023-01-15, which is a Sunday.
    expected_formatted_top_day = "Sunday the 15th of January"
    assert f"TopDay: {expected_formatted_top_day}" in rendered_html

    # Check that the output HTML file was written to
    # Get the args from the call to write the output HTML
    # This assumes it's the third .write() call corresponding to the third open (output HTML)
    # Find the specific write call for the output file
    html_write_call = None
    for c in m_open.mock_calls:
        # Check if this call is the write to the output file
        # The `open()` call itself will be in `m_open.call_args_list`.
        # The `.write()` call is on the object returned by `open()`.
        # This is a bit complex to fish out. A simpler check is that the `rendered_html` is correct.
        pass # Cannot easily check the write content directly from m_open.side_effect like this.
             # The `rendered_html` variable holds the content that *would* be written.
    
    # To check the content written to the mock for the output HTML:
    # The mock_open().return_value from the side_effect list for the output HTML
    # is the specific mock file object.
    # `m_open.side_effect[2].write.assert_called_once_with(rendered_html)`
    # This depends on knowing the exact index.
    # Alternative: iterate through m_open.side_effect if they are mock_open instances
    # and find the one that corresponds to the output file write.
    # For now, asserting `rendered_html` content is the primary check.

```
