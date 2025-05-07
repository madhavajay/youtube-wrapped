import json
import requests
import warnings
import os
import pandas as pd
import re
import requests
import json
import os

import isodate
import tzlocal
from tqdm import tqdm
from utils import YoutubeDataPipelineState


METADATA_FILE = 'cache/youtube_metadata.json'

def load_metadata_cache():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_metadata_cache(cache):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def fetch_video_metadata(video_id, api_key, cache):
    if video_id in cache and cache[video_id] is not None:
        return cache[video_id]

    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics&id={video_id}&key={api_key}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()

        if 'items' in data and data['items']:
            metadata = data['items'][0]
            cache[video_id] = metadata
            return metadata
        else:
            warning_message = f"Warning: Video ID {video_id} not found or inaccessible."
            return warning_message
    except Exception as e:
        error_message = str(e)
        print(f"Error fetching metadata for Video ID {video_id}: {error_message}")
        return error_message

def extract_video_id(video_link):
    match = re.search(r'v=([^&]+)', video_link)
    return match.group(1) if match else None

def get_duration_seconds_from_metadata(metadata):
    if metadata and 'contentDetails' in metadata and 'duration' in metadata['contentDetails']:
        duration_iso = metadata['contentDetails']['duration']
        try:
            duration = isodate.parse_duration(duration_iso)
            return int(duration.total_seconds())
        except Exception as e:
            print(f"Error parsing duration: {e}")
            return None
    return None

def fetch_and_save_youtube_category_mapping(api_key: str, region_code: str = 'US', output_file: str = 'cache/youtube_category_region.json') -> dict:
        """
        Fetch YouTube video categories, save to a file, and return a mapping of category ID to category Title.
        If the output file already exists, load and return it instead of fetching.

        Args:
            api_key (str): Your YouTube Data API v3 key.
            region_code (str): The region code for categories (default: 'US').
            output_file (str): The filename to save/load the category mapping (default: 'youtube_category_region.json').

        Returns:
            dict: Mapping of category ID (as str) to category Title.
        """
        if os.path.exists(output_file):
            # Load and return existing file
            with open(output_file, 'r', encoding='utf-8') as f:
                category_mapping = json.load(f)
            return category_mapping

        # Otherwise fetch from the API
        url = 'https://www.googleapis.com/youtube/v3/videoCategories'
        params = {
            'part': 'snippet',
            'regionCode': region_code,
            'key': api_key
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        category_mapping = {item['id']: item['snippet']['title'] for item in data.get('items', [])}

        # Save to JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(category_mapping, f, ensure_ascii=False, indent=2)

        return category_mapping


def process_rows(youtube_api_key: str, watch_history_path: str, enriched_data_path: str, n: int = 10, year_filter: int = None):
    pipeline_state = YoutubeDataPipelineState()

    if not pipeline_state.is_keep_running():
        return

    # Load your existing watch history
    df = pd.read_csv(watch_history_path)

    # Step 1: Parse datetime normally, ignoring warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=UserWarning)
        df['watch_time_dt'] = pd.to_datetime(df['watch_time'], errors='coerce')

    # Step 2: Detect system timezone
    local_timezone = tzlocal.get_localzone()

    # Step 3: Fix timezone correctly for each row
    def fix_timezone(dt):
        if pd.isna(dt):
            return dt
        if dt.tzinfo is None:
            # Naive datetime, localize it
            return dt.tz_localize(local_timezone)
        else:
            # Already timezone-aware, just convert
            return dt.tz_convert(local_timezone)

    df['watch_time_dt'] = df['watch_time_dt'].apply(fix_timezone)

    # Assuming your parsed datetime is in 'watch_time_dt'
    if year_filter:
        # Filter for rows where the year matches
        df = df[df['watch_time_dt'].dt.year == year_filter]
    # Load metadata cache
    cache = load_metadata_cache()

    durations = []
    categories = []
    errors = []
    if 'duration_seconds' not in df.columns:
        df['duration_seconds'] = None
    if 'category_id' not in df.columns:
        df['category_id'] = None
    if 'category_name' not in df.columns:
        df['category_name'] = None
    if 'error' not in df.columns:
        df['error'] = None

    # Load the processed rows if they exist
    if os.path.exists(enriched_data_path):
        processed_df = pd.read_csv(enriched_data_path)

        # Remove processed rows from the main DataFrame
        df = df[~df[['video_link', 'watch_time']].apply(tuple, axis=1).isin(processed_df[['video_link', 'watch_time']].apply(tuple, axis=1))]


    links_to_process = df.head(n)

    previous_cache_len = len(cache)

    for idx, link in tqdm(zip(links_to_process.index, links_to_process['video_link']), total=len(links_to_process), desc="Fetching metadata"):
        video_id = extract_video_id(link)
        if video_id:
            metadata = fetch_video_metadata(video_id, youtube_api_key, cache)
            if isinstance(metadata, str):
                errors.append((idx, metadata))
            else:
                errors.append((idx, None))
                # Extract duration
                duration_seconds = get_duration_seconds_from_metadata(metadata)

                # Extract categoryId
                category_id = None
                if metadata and 'snippet' in metadata and 'categoryId' in metadata['snippet']:
                    category_id = metadata['snippet']['categoryId']
                durations.append((idx, duration_seconds))
                categories.append((idx, category_id))
        else:
            durations.append((idx, None))
            categories.append((idx, None))
            errors.append((idx, "Video ID not found"))


    # Save cache only if it grows
    if len(cache) > previous_cache_len:
        save_metadata_cache(cache)
        previous_cache_len = len(cache)

    mapping = fetch_and_save_youtube_category_mapping(youtube_api_key)


    # Create or reset the columns
    links_to_process['duration_seconds'] = None
    links_to_process['category_id'] = None

    # Apply extracted values back to DataFrame
    for idx, dur in durations:
        links_to_process.at[idx, 'duration_seconds'] = dur

    for idx, cat_id in categories:
        links_to_process.at[idx, 'category_id'] = cat_id

    for idx, err in errors:
        links_to_process.at[idx, 'error'] = err

    links_to_process['category_name'] = links_to_process['category_id'].map(mapping)

    # Load the enriched data
    if os.path.exists(enriched_data_path):
        enriched_df = pd.read_csv(enriched_data_path)
        print("current length of enriched_df", len(enriched_df))

        # Combine the existing filtered df with the enriched_df
        combined_df = pd.concat([links_to_process, enriched_df], ignore_index=True)

        # Update the original df with the combined data
        links_to_process = combined_df

    # Save the enriched file
    links_to_process.to_csv(enriched_data_path, index=False)

    print(f"✅ Done! Enriched file saved as {enriched_data_path}")