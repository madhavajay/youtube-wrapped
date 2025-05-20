from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import dateparser
import jinja2
import pandas as pd
import requests
from fastapi import BackgroundTasks, FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastsyftbox import Syftbox
from loguru import logger
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig
from syft_event import SyftEvents

from metadata import process_rows
from resources import add_dataset, ensure_syft_yaml
from utils import YoutubeDataPipelineState
from wrapped import generate_wrapped_json

syftbox_domain = "https://syftboxdev.openmined.org"

box = SyftEvents("youtube-wrapped")

config = SyftClientConfig.load()
client = SyftboxClient(config)
app_name = "youtube-wrapped"
wrapped_path = client.datasite_path / "public" / app_name
client.makedirs(wrapped_path)

app_data_dir = Path(client.config.data_dir) / "private" / "app_data" / app_name
app_data_dir.mkdir(parents=True, exist_ok=True)

cache_dir = app_data_dir / "cache"
cache_dir.mkdir(parents=True, exist_ok=True)

data_dir = app_data_dir / "data"
data_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(debug=True)
syftbox = Syftbox(app=app, name=app_name)


# @syftbox.on_request("/ping")
# def ping_handler(ping: PingRequest) -> PongResponse:
#     """Handle a ping request and return a pong response."""
#     logger.info(f"Got ping request - {ping}")
#     return PongResponse(
#         msg=f"Pong from {box.client.email}",
#         ts=datetime.now(timezone.utc),
#     )

ensure_syft_yaml(client)

current_dir = Path(__file__).parent

# Serve static files from the assets/images directory
app.mount(
    "/images", StaticFiles(directory=current_dir / "assets" / "images"), name="images"
)
app.mount("/js", StaticFiles(directory=current_dir / "assets" / "js"), name="js")


def find_youtube_wrapped_html_files(base_path):
    """
    Searches the given base path for all HTML files located in the
    */public/youtube-wrapped/* directory structure.

    Args:
        base_path (Path): The base directory to start the search from.

    Returns:
        List[Path]: A list of Paths to the found HTML files.
    """
    youtube_wrapped_path = base_path.glob("*/public/youtube-wrapped/*.html")
    html_files = list(youtube_wrapped_path)
    print(html_files)
    html_files = [
        f"{syftbox_domain}/datasites/{str(file).split('/datasites/', 1)[1]}"
        for file in html_files
    ]
    html_files_dict = {}
    for file_url in html_files:
        # Extract the email from the URL
        email = file_url.split("/")[4]
        if email not in html_files_dict:
            html_files_dict[email] = []
        html_files_dict[email].append(file_url)

    # Sort the list of files for each email
    for email in html_files_dict:
        html_files_dict[email].sort()

    return html_files_dict


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui_home(request: Request):
    try:
        other_files = find_youtube_wrapped_html_files(client.datasites)
        print(other_files)
    except Exception as e:
        other_files = {}
        logger.error(f"An error occurred while finding other files: {e}")

    pipeline_state = YoutubeDataPipelineState(app_data_dir)
    template_path = current_dir / "assets" / "home.html"

    with open(template_path) as f:
        template_content = f.read()

    years = pipeline_state.get_years()
    year_stats = []

    try:
        if pipeline_state.enriched_data_exists():
            for year in years:
                json_file_path = cache_dir / f"youtube-wrapped-{year}.json"
                if not json_file_path.exists():
                    generate_wrapped_json(year, data_dir, cache_dir)

                if json_file_path.exists():
                    with open(json_file_path, "r") as json_file:
                        stats = json.load(json_file)
                        published = (
                            wrapped_path / f"youtube-wrapped-{year}.html"
                        ).exists()
                        year_stats.append(
                            {
                                "total_views": int(stats["total_views"]),
                                "total_hours": int(stats["total_hours"]),
                                "total_days": int(stats["total_days"]),
                                "average_per_day": f"{stats['average_hours']}:{stats['average_minutes']:02d}",
                                "year": year,
                                "published": published,
                            }
                        )

            json_file_path = cache_dir / "youtube-wrapped-all.json"
            if not json_file_path.exists():
                generate_wrapped_json("all", data_dir, cache_dir)
            if json_file_path.exists():
                with open(json_file_path, "r") as json_file:
                    stats = json.load(json_file)
                    published = (wrapped_path / "youtube-wrapped-all.html").exists()
                    year_stats.append(
                        {
                            "total_views": int(stats["total_views"]),
                            "total_hours": int(stats["total_hours"]),
                            "total_days": int(stats["total_days"]),
                            "average_per_day": f"{stats['average_hours']}:{stats['average_minutes']:02d}",
                            "year": "all",
                            "published": published,
                        }
                    )
    except Exception as e:
        logger.error(f"An error occurred while generating wrapped cache json: {e}")

    template = jinja2.Template(template_content)

    wrapped_url = f"{syftbox_domain}/datasites/{client.email}/public/youtube-wrapped/"
    render_context = {
        "source_data_exists": pipeline_state.source_data_exists(),
        "enriched_data_exists": pipeline_state.enriched_data_exists(),
        "step_3_summarize": pipeline_state.step_3_summarize(),
        "step_4_publish": pipeline_state.step_4_publish(),
        "setup_api_key": pipeline_state.setup_api_key(),
        "watch_history_path": pipeline_state.get_watch_history_path(),
        "watch_history_csv_path": pipeline_state.get_watch_history_csv_path(),
        "watch_history_file_size_mb": pipeline_state.get_watch_history_file_size_mb(),
        "total_rows": pipeline_state.get_total_rows(),
        "is_processing": pipeline_state.is_processing(),
        "processed_rows": pipeline_state.get_processed_rows(),
        "enriched_data_path": pipeline_state.get_enriched_data_path(),
        "enriched_rows": pipeline_state.get_enriched_rows(),
        "missing_rows": pipeline_state.get_missing_rows(),
        "is_complete": bool(
            pipeline_state.get_processed_rows() == pipeline_state.get_total_rows()
        ),
        "years": year_stats,
        "wrapped_url": wrapped_url,
        "other_files": other_files,
        "syftbox_domain": syftbox_domain,
    }

    # print(render_context)

    rendered_content = template.render(**render_context)

    return HTMLResponse(rendered_content)


@app.get("/summarize", response_class=JSONResponse, include_in_schema=False)
async def summarize(request: Request, year: int | str = datetime.now().year - 1):
    try:
        other_files = find_youtube_wrapped_html_files(client.datasites)
        print(other_files)
    except Exception:
        other_files = {}

    pipeline_state = YoutubeDataPipelineState(app_data_dir)

    from share_image import create_share_image
    from wrapped import create_wrapped_page

    create_share_image(year, app_data_dir, cache_dir / f"youtube-wrapped-{year}.png")
    rendered_html = create_wrapped_page(
        year, client, data_dir, cache_dir, other_files, syftbox_domain
    )

    return HTMLResponse(rendered_html)


@app.post("/start-processing", include_in_schema=False)
async def start_processing(request: Request, background_tasks: BackgroundTasks):
    pipeline_state = YoutubeDataPipelineState(app_data_dir)

    # Check if source data exists and API key is set up
    if not (pipeline_state.source_data_exists() and pipeline_state.setup_api_key()):
        return JSONResponse(
            {"success": False, "error": "Preconditions not met."}, status_code=400
        )

    # Mark processing as started
    pipeline_state.set_processing(True)
    pipeline_state.set_keep_running(True)

    # Run process_rows in the background
    def run_process():
        pipeline_state = YoutubeDataPipelineState(app_data_dir)
        youtube_api_token = None
        config_path = cache_dir / "config.json"
        if config_path.exists():
            with config_path.open("r") as config_file:
                config_data = json.load(config_file)
                youtube_api_token = config_data.get("youtube-api-key", "")

        try:
            process_rows(
                client=client,
                youtube_api_key=youtube_api_token,
                app_data_dir=app_data_dir,
                watch_history_path=pipeline_state.get_watch_history_csv_path(),
                enriched_data_path=pipeline_state.get_enriched_data_path(),
            )
        finally:
            # Check if processing is still marked as true
            if pipeline_state.is_keep_running():
                # Add another background task to keep processing
                background_tasks.add_task(run_process)
            else:
                # Mark processing as finished
                pipeline_state.set_processing(False)

    background_tasks.add_task(run_process)

    return JSONResponse({"success": True, "message": "Processing started."})


@app.post("/stop-processing", include_in_schema=False)
async def stop_processing(request: Request, background_tasks: BackgroundTasks):
    pipeline_state = YoutubeDataPipelineState(app_data_dir)

    pipeline_state.set_keep_running(False)

    # Clear background tasks to stop any further processing
    background_tasks.tasks.clear()

    # Mark processing as stopped
    pipeline_state.set_processing(False)

    return JSONResponse({"success": True, "message": "Processing has been stopped."})


@app.get("/processing-status", response_class=JSONResponse, include_in_schema=False)
async def processing_status():
    pipeline_state = YoutubeDataPipelineState(app_data_dir)

    # Check if processing is ongoing
    is_processing = pipeline_state.is_processing()

    # Get the current processing stats

    total_rows = pipeline_state.get_total_rows()
    processed_rows = pipeline_state.get_processed_rows()
    enriched_rows = pipeline_state.get_enriched_rows()
    missing_rows = pipeline_state.get_missing_rows()

    return JSONResponse(
        {
            "is_processing": bool(is_processing),
            "total_rows": int(total_rows),
            "processed_rows": int(processed_rows),
            "enriched_rows": int(enriched_rows),
            "missing_rows": int(missing_rows),
            "is_complete": bool(processed_rows == total_rows),
        }
    )


@app.get("/download", response_class=HTMLResponse, include_in_schema=False)
async def ui_download(request: Request):
    pipeline_state = YoutubeDataPipelineState(app_data_dir)
    template_path = current_dir / "assets" / "download.html"

    with open(template_path) as f:
        template_content = f.read()

    template = jinja2.Template(template_content)

    rendered_content = template.render()

    return HTMLResponse(rendered_content)


async def process_upload(upload_path):
    syft_uri = f"syft://{client.email}/private/youtube-wrapped/watch-history.html"
    private_path = upload_path
    schema_name = "com.google.takeout.youtube.watch-history:1.0.0"
    add_dataset(client, "watch-history-raw-html", syft_uri, private_path, schema_name)

    import html as ihtml
    import re

    from tqdm import tqdm

    # Load the HTML file
    with open(upload_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Find all "outer-cell" blocks quickly without full DOM parsing
    entries = re.findall(r'<div class="outer-cell[\s\S]*?<\/div>\s*<\/div>', html)

    data = []

    for entry in tqdm(entries, desc="Processing entries"):
        if "Watched" not in entry:
            continue  # Skip anything not related to a watched video

        # ✅ Correctly extract only the first "content-cell" div (the real watch event)
        match = re.search(
            r'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">(.*?)<\/div>',
            entry,
            re.S,
        )
        if not match:
            continue

        watched_section = match.group(1)

        if watched_section.strip().startswith("https://"):
            continue  # Skip bad auto-logged links

        # Extract all links
        links = re.findall(r'<a href="(.*?)">(.*?)<\/a>', watched_section)
        # Step 1: Parse HTML
        text_blocks = [
            line.strip()
            for line in re.split(r"<[^>]+>", watched_section)
            if line.strip()
        ]
        text_blocks = [text_blocks[-1]]
        # Step 2: Try parsing each line for a datetime
        watch_time = None
        for line in reversed(text_blocks):  # Start from end=
            try:
                dt = dateparser.parse(line)
                watch_time = dt.isoformat()
                break  # Stop at first successful parse from the end
            except Exception:
                continue

        if not watch_time:
            print(f"❌ No valid datetime found in watched_section {watched_section}")
            continue

        # --- CASE 1: Full record with video and channel
        if len(links) >= 2 and watch_time:
            video_link, video_name = links[0]
            channel_link, channel_name = links[1]

            video_name_unescaped = ihtml.unescape(video_name.strip())
            channel_name_unescaped = ihtml.unescape(channel_name.strip())

            # ❗ Skip if video name is same as link
            if video_name_unescaped.strip() == video_link.strip():
                continue

            data.append(
                {
                    "video_name": video_name_unescaped,
                    "video_link": video_link.strip(),
                    "channel_name": channel_name_unescaped,
                    "channel_link": channel_link.strip(),
                    "watch_time": watch_time.strip(),
                }
            )
            continue

        # --- CASE 2: Minimal record with only video
        if len(links) >= 1 and watch_time:
            video_link, video_name = links[0]

            video_name_unescaped = ihtml.unescape(video_name.strip())

            # Fallback: if name is same as link, use video ID as name
            if video_name_unescaped.strip() == video_link.strip():
                # from urllib.parse import urlparse, parse_qs
                # qs = parse_qs(urlparse(video_link).query)
                # video_name_unescaped = qs.get("v", [video_link])[-1]  # use video ID
                video_name_unescaped = ""

            data.append(
                {
                    "video_name": video_name_unescaped,
                    "video_link": video_link.strip(),
                    "channel_name": "",  # not available
                    "channel_link": "",  # not available
                    "watch_time": watch_time.strip(),
                }
            )
            continue

        else:
            continue

    # Create DataFrame
    df = pd.DataFrame(data)

    # Save to CSV
    df.to_csv(data_dir / "watch-history.csv", index=False)

    syft_uri = f"syft://{client.email}/private/youtube-wrapped/watch-history.csv"
    private_path = data_dir / "watch-history.csv"
    schema_name = "com.madhavajay.youtube-wrapped.watch-history-raw:1.0.0"
    add_dataset(client, "watch-history-raw-csv", syft_uri, private_path, schema_name)

    print(f"Debug: Extracted {len(df)} entries and saved to watch-history.csv")


@app.post("/upload", include_in_schema=False)
async def upload_watch_history(request: Request):
    print("Debug: Starting upload_watch_history function.")
    form = await request.form()
    file: UploadFile = form.get("file-input")

    if not file:
        print("Debug: No file uploaded.")
        return HTMLResponse("No file uploaded.", status_code=400)

    contents = await file.read()
    print(f"Debug: Uploaded file name: {file.filename}")
    print(f"Debug: Uploaded file size: {len(contents)} bytes")

    if len(contents) == 0:
        print("Debug: Uploaded file is empty.")
        return HTMLResponse("Uploaded file is empty.", status_code=400)

    upload_path = data_dir / "watch-history.html"
    with open(upload_path, "wb") as f:
        f.write(contents)
    print(f"Debug: File written to {upload_path}")

    await process_upload(upload_path)

    return RedirectResponse(url="/", status_code=303)


@app.api_route("/api", methods=["GET", "POST"])
async def api_setup(request: Request):
    """Endpoint to enrich watch history data."""
    config_path = cache_dir / "config.json"

    # Check if the config file exists and load the API key
    youtube_api_token = None
    if config_path.exists():
        with config_path.open("r") as config_file:
            config_data = json.load(config_file)
            youtube_api_token = config_data.get("youtube-api-key", "")

    # Render the HTML with Jinja2, injecting the API key if it exists
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(current_dir / "assets"))
    template = env.get_template("api.html")
    rendered_html = template.render(youtube_api_key=youtube_api_token or "")

    if request.method == "GET":
        return HTMLResponse(content=rendered_html, media_type="text/html")

    elif request.method == "POST":
        form_data = await request.form()
        youtube_api_token = form_data.get("youtube-api-key", "").strip()

        config_path = cache_dir / "config.json"
        existing_api_token = None

        if config_path.exists():
            with config_path.open("r") as config_file:
                config_data = json.load(config_file)
                existing_api_token = config_data.get("youtube-api-key", "")

        if youtube_api_token and youtube_api_token != existing_api_token:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={
                    "part": "id,snippet",
                    "forUsername": "GoogleDevelopers",  # OR use "id" param for channel ID
                    "key": youtube_api_token,
                },
            )

            if response.status_code != 200:
                return JSONResponse(
                    content={"error": "Invalid YouTube API token"}, status_code=400
                )

            config_data = {"youtube-api-key": youtube_api_token}
            with config_path.open("w") as config_file:
                json.dump(config_data, config_file)

        if not youtube_api_token:
            return JSONResponse(
                content={"error": "YouTube API token is required"}, status_code=400
            )

        # Here you would add the logic to use the YouTube API token to enrich the watch history
        # For now, we'll just log the token and return a success message
        logger.info(f"Received YouTube API token: {youtube_api_token}")

        return RedirectResponse(url="/", status_code=303)


@app.get("/publish", include_in_schema=False)
async def publish(year: int | str):
    """Endpoint to publish a wrapped HTML file for a given year."""

    try:
        other_files = find_youtube_wrapped_html_files(client.datasites)
        print(other_files)
    except Exception:
        other_files = {}

    wrapped_path = client.datasite_path / "public" / app_name

    from share_image import create_share_image
    from wrapped import create_wrapped_page

    create_share_image(year, app_data_dir, cache_dir / f"youtube-wrapped-{year}.png")
    create_wrapped_page(year, client, data_dir, cache_dir, other_files, syftbox_domain)

    shutil.copy(
        cache_dir / f"youtube-wrapped-{year}.html",
        wrapped_path / f"youtube-wrapped-{year}.html",
    )
    if not (cache_dir / f"youtube-wrapped-{year}.png").exists():
        from share_image import create_share_image

        create_share_image(
            year, app_data_dir, cache_dir / f"youtube-wrapped-{year}.png"
        )
    shutil.copy(
        cache_dir / f"youtube-wrapped-{year}.png",
        wrapped_path / f"youtube-wrapped-{year}.png",
    )
    return RedirectResponse(url="/", status_code=303)


@app.get("/delete-enriched", include_in_schema=False)
async def delete_enriched():
    """Endpoint to delete the enriched watch history CSV file."""
    try:
        enriched_file_path = data_dir / "watch-history-enriched.csv"
        if enriched_file_path.exists():
            os.remove(enriched_file_path)
    except Exception as e:
        logger.error(f"An error occurred while deleting the enriched file: {e}")
    return RedirectResponse(url="/", status_code=303)


@app.get("/unpublish", include_in_schema=False)
async def unpublish(year: int | str):
    """Endpoint to publish a wrapped HTML file for a given year."""
    wrapped_path = client.datasite_path / "public" / app_name

    if (wrapped_path / f"youtube-wrapped-{year}.html").exists():
        os.remove(wrapped_path / f"youtube-wrapped-{year}.html")
    if (wrapped_path / f"youtube-wrapped-{year}.png").exists():
        os.remove(wrapped_path / f"youtube-wrapped-{year}.png")
    return RedirectResponse(url="/", status_code=303)


@app.get("/launch-takeout-agent", include_in_schema=False)
async def launch_takeout_agent():
    from helper import automate_takeout

    try:
        await automate_takeout(cache_dir)
    except Exception as e:
        logger.error(f"An error occurred while launching the takeout agent: {e}")
    return RedirectResponse(url="/download", status_code=303)


@app.get("/launch-gmail-download-agent", include_in_schema=False)
async def launch_gmail_download_agent():
    from helper import automate_download_email_link

    try:
        await automate_download_email_link(cache_dir)
    except Exception as e:
        logger.error(f"An error occurred while closing the page: {e}")

    try:
        watch_history_path = data_dir / "watch-history.html"
        if watch_history_path.exists():
            await process_upload(watch_history_path)
    except Exception as e:
        logger.error(f"An error occurred while launching the takeout agent: {e}")
    return RedirectResponse(url="/", status_code=303)
