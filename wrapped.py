
import pandas as pd
import json
import re
import warnings
import tzlocal

from jinja2 import Template
import datetime
import pandas as pd
from datetime import datetime

def format_human_date(dt: datetime) -> str:
    # Suffix helper
    def ordinal(n):
        if 11 <= n % 100 <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    return f"{dt.strftime('%A')} the {ordinal(dt.day)} of {dt.strftime('%B')}"


def generate_wrapped_json(year: int | str):
    # Load your CSV
    df = pd.read_csv(f'./data/watch-history-enriched.csv')

    # Step 1: Parse datetime normally
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
    
    # Step 1: Parse datetime normally, ignoring warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=UserWarning)
        df['watch_time_dt'] = pd.to_datetime(df['watch_time'], errors='coerce')

    # import pandas as pd
    # import matplotlib.pyplot as plt
    # # Assuming df is your DataFrame and 'duration_seconds' is filled correctly
    # # Step 1: Define duration in hours
    # df['duration_hours'] = df['duration_seconds'] / 3600
    # # Step 2: Bin durations into categories
    # bins = list(range(0, 13)) + [float('inf')]  # 0–1, 1–2, ..., 11–12, 12+
    # labels = [f"{i}-{i+1}" for i in range(0, 12)] + ['12+']
    # df['duration_bucket'] = pd.cut(df['duration_hours'], bins=bins, labels=labels, right=False)
    # # Step 3: Count videos in each bucket
    # histogram = df['duration_bucket'].value_counts().sort_index()
    # print(histogram)
    # # Step 4: Optional: plot it
    # histogram.plot(kind='bar')
    # plt.title('Number of Videos by Duration Bucket')
    # plt.xlabel('Duration (hours)')
    # plt.ylabel('Number of Videos')
    # plt.xticks(rotation=45)
    # plt.grid(axis='y')
    # plt.tight_layout()
    # plt.show()

    # remove errors
    df = df[df['error'].isna()]

    # remove things over 4 hours (usually infinite loop videos)
    df = df[df['duration_seconds'] <= 4 * 3600]


    if year != "all":
        year = int(year)
    # Filter for rows where the year matches
        df_year = df[df['watch_time_dt'].dt.year == year]
    else:
        df_year = df

    json_stats = {}
    json_stats["year"] = year

    top_categories = (
        df['category_name']
        .dropna()
        .value_counts()
        .head(5)
    )
    top_categories

    json_stats["top_categories"] = list(top_categories.keys())

    top_channels = (
        df_year
        .assign(minutes=df_year['duration_seconds'].fillna(0) / 60)
        .groupby('channel_name')['minutes']
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .to_dict()
    )

    json_stats["top_channels"] = list(top_channels.keys())

    # First get top channels' names
    top_channel_names = (
        df_year
        .assign(minutes=df_year['duration_seconds'].fillna(0) / 60)
        .groupby('channel_name')['minutes']
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .index.tolist()
    )
    # Now build a list of (channel_name, channel_link)
    top_channels_with_links = (
        df_year
        .drop_duplicates(subset=['channel_name'])  # Remove duplicates first
        .set_index('channel_name')                 # Set channel_name as index
        .loc[top_channel_names]                    # Select only top channels
        [['channel_link']]                         # Only keep channel_link
        .reset_index()
        .values.tolist()
    )

    top_channels_with_links

    json_stats["top_channels_links"] = [link[1] for link in top_channels_with_links]

    json_stats["top_channels_links"]

    
    def extract_video_id(video_link):
        match = re.search(r'v=([^&]+)', video_link)
        return match.group(1) if match else None

    # Get top 5 videos by minutes watched
    top_video_names = (
        df_year['video_name']
        .value_counts()
        .head(5)
        .index.tolist()
    )
    # Now fetch the video_link and construct thumbnail
    top_videos_with_links_and_thumbs = []
    for video_name in top_video_names:
        row = (
            df_year[df_year['video_name'] == video_name]
            .drop_duplicates(subset=['video_name'])  # Just in case
            .iloc[0]
        )
        video_link = row['video_link']
        video_id = extract_video_id(video_link)
        if video_id:
            thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
        else:
            thumbnail = "/api/placeholder/80/60"  # fallback if parsing failed
        top_videos_with_links_and_thumbs.append(
            (video_name, thumbnail, video_link)
        )

    json_stats["top_videos_links"] = [link[2] for link in top_videos_with_links_and_thumbs]

    json_stats["top_videos_thumbs"] = [link[1] for link in top_videos_with_links_and_thumbs]

    top_videos = (
        df_year['video_name']
        .value_counts()
        .head(5)
        .to_dict()
    )

    json_stats["top_videos"] = list(top_videos.keys())

    total_views = len(df_year)

    json_stats["total_views"] = total_views

    total_minutes = df_year['duration_seconds'].sum() // 60
    total_minutes

    json_stats["total_hours"] = int(total_minutes // 60)

    json_stats["total_minutes"] = int(total_minutes - int(total_minutes // 60))

    top_day = (
        df_year['watch_time_dt']
        .dt.day_name()
        .value_counts()
        .idxmax()
    )

    json_stats["top_day"] = top_day

    # Assuming you already filtered your df to a year like df_year
    days_watched = df_year['watch_time_dt'].dt.date.nunique()

    json_stats["total_days"] = days_watched

    average_minutes_per_day = total_minutes / days_watched if days_watched > 0 else 0
    
    # average_minutes_per_day is already calculated
    average_hours = int(average_minutes_per_day // 60)
    average_minutes = int(average_minutes_per_day % 60)

    json_stats["average_hours"] = average_hours
    json_stats["average_minutes"] = average_minutes

    # Group by date and sum minutes watched
    minutes_per_day = (
        df_year
        .assign(minutes=df_year['duration_seconds'].fillna(0) / 60)
        .groupby(df_year['watch_time_dt'].dt.date)['minutes']
        .sum()
    )
    if not minutes_per_day.empty:
        top_day = minutes_per_day.idxmax()
        top_minutes = minutes_per_day.max()

        # Convert top_day to pandas Timestamp to easily get day of week
        top_day_dt = pd.to_datetime(top_day)
        top_day_name = top_day_dt.day_name()

        json_stats["top_day_date_year"] = top_day.year
        json_stats["top_day_date_month"] = top_day.month
        json_stats["top_day_date_day"] = top_day.day
        json_stats["top_day_date_day_name"] = top_day_name
        json_stats["top_day_minutes"] = int(top_minutes)
    else:
        json_stats["top_day_date_year"] = None
        json_stats["top_day_date_month"] = None
        json_stats["top_day_date_day"] = None
        json_stats["top_day_date_day_name"] = None
        json_stats["top_day_minutes"] = 0
    
    with open(f"./cache/youtube-wrapped-{year}.json", "w") as f:
        f.write(json.dumps(json_stats))


def create_wrapped_page(year: int | str):
    generate_wrapped_json(year)

    data = {}
    with open(f"./cache/youtube-wrapped-{year}.json", "r") as f:
        data = json.load(f)

    # Prepare processed fields
    data["top_channels_combined"] = list(zip(data["top_channels"], data["top_channels_links"]))
    data["top_videos_combined"] = list(zip(data["top_videos"], data["top_videos_thumbs"], data["top_videos_links"]))

    top_date_dt = pd.to_datetime(f"{data['top_day_date_day']:02d}-{data['top_day_date_month']:02d}-{data['top_day_date_year']}", dayfirst=True)

    data["top_day_date"] = format_human_date(top_date_dt)

    with open("./assets/wrapped-template.html", "r", encoding="utf-8") as f:
        template_html = f.read()

    template = Template(template_html)

    # Render the final HTML
    rendered_html = template.render(
        year=data["year"],
        total_hours=data["total_hours"],
        total_minutes=data["total_minutes"],
        average_hours=data["average_hours"],
        average_minutes=data["average_minutes"],
        top_day_date=data["top_day_date"],
        top_day_minutes=data["top_day_minutes"],
        top_channels=data["top_channels_combined"],
        top_videos=data["top_videos_combined"],
        category_names=data["top_categories"],
        total_days=data["total_days"],
    )

    # Write to output file
    with open(f'./cache/youtube-wrapped-{year}.html', 'w', encoding='utf-8') as f:
        f.write(rendered_html)

    return rendered_html
