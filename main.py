from __future__ import annotations
import asyncio
import json
from fastapi import UploadFile, File
from pathlib import Path
from fastapi.responses import RedirectResponse
from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from datetime import datetime, timezone

from loguru import logger
from pydantic import BaseModel, Field
from syft_event import SyftEvents
import jinja2

class YoutubeDataPipelineState:
    def __init__(self):
        self.paths = {
            "watch_history": Path("data/watch-history.html"),
            "watch_history_enriched": Path("data/watch-history-enriched.csv"),
            "watch_history_summary": Path("data/watch-history-summary.json"),
            "youtube_wrapped": Path("data/youtube-wrapped.html")
        }
        self.config_path = Path("cache/config.json")

    def step_1_download(self) -> bool:
        return self.paths["watch_history"].exists()

    def step_2_enrich(self) -> bool:
        return self.paths["watch_history_enriched"].exists()

    def step_3_summarize(self) -> bool:
        return self.paths["watch_history_summary"].exists()

    def step_4_publish(self) -> bool:
        return self.paths["youtube_wrapped"].exists()

    def setup_api_key(self) -> bool:
        if self.config_path.exists():
            with self.config_path.open("r") as config_file:
                config_data = json.load(config_file)
                return "youtube-api-key" in config_data
        return False


box = SyftEvents("youtube-wrapped")


# @box.on_request("/ping")
# def ping_handler(ping: PingRequest) -> PongResponse:
#     """Handle a ping request and return a pong response."""
#     logger.info(f"Got ping request - {ping}")
#     return PongResponse(
#         msg=f"Pong from {box.client.email}",
#         ts=datetime.now(timezone.utc),
#     )


app = FastAPI()
current_dir = Path(__file__).parent

# Serve static files from the assets/images directory
app.mount("/images", StaticFiles(directory=current_dir / "assets" / "images"), name="images")


async def async_run_box():
    await asyncio.to_thread(box.run_forever)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui_home(request: Request):
    pipeline_state = YoutubeDataPipelineState()
    template_path = current_dir / "assets" / "home.html"
    
    with open(template_path) as f:
        template_content = f.read()
    
    template = jinja2.Template(template_content)

    rendered_content = template.render(
        step_1_download=pipeline_state.step_1_download(),
        step_2_enrich=pipeline_state.step_2_enrich(),
        step_3_summarize=pipeline_state.step_3_summarize(),
        step_4_publish=pipeline_state.step_4_publish(),
        setup_api_key=pipeline_state.setup_api_key()
    )

    return HTMLResponse(rendered_content)

@app.get("/download", response_class=HTMLResponse, include_in_schema=False)
async def ui_download(request: Request):
    pipeline_state = YoutubeDataPipelineState()
    template_path = current_dir / "assets" / "download.html"
    
    with open(template_path) as f:
        template_content = f.read()
    
    template = jinja2.Template(template_content)

    rendered_content = template.render()

    return HTMLResponse(rendered_content)

@app.post("/upload", include_in_schema=False)
async def upload_watch_history(request: Request):
    form = await request.form()
    file: UploadFile = form.get("file-input")

    if not file:
        print("Debug: No file uploaded.")
        return HTMLResponse("No file uploaded.", status_code=400)

    contents = await file.read()
    print(f"Debug: Uploaded file name: {file.filename}")
    print(f"Debug: Uploaded file size: {len(contents)} bytes")

    if len(contents) == 0:
        return HTMLResponse("Uploaded file is empty.", status_code=400)

    upload_path = current_dir / "data" / "watch-history.html"
    with open(upload_path, "wb") as f:
        f.write(contents)

    import re
    import pandas as pd
    from tqdm import tqdm
    import html as ihtml

    # Load the HTML file
    with open('watch-history.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Find all "outer-cell" blocks quickly without full DOM parsing
    entries = re.findall(r'<div class="outer-cell[\s\S]*?<\/div>\s*<\/div>', html)

    print(len(entries))

    data = []

    for entry in tqdm(entries, desc="Processing entries"):
        if "Watched" not in entry:
            continue  # Skip anything not related to a watched video

        # ✅ Correctly extract only the first "content-cell" div (the real watch event)
        match = re.search(r'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">(.*?)<\/div>', entry, re.S)
        if not match:
            continue
        
        watched_section = match.group(1)


        if watched_section.strip().startswith("https://"):
            continue  # Skip bad auto-logged links

        # Extract all links
        links = re.findall(r'<a href="(.*?)">(.*?)<\/a>', watched_section)
        # Extract timestamps
        time_match = re.search(r'(\d{1,2} \w+ \d{4}, \d{2}:\d{2}:\d{2} [A-Z]+)', watched_section)

        # --- CASE 1: Full record with video and channel
        if len(links) >= 2 and time_match:
            video_link, video_name = links[0]
            channel_link, channel_name = links[1]
            watch_time = time_match.group(1)

            video_name_unescaped = ihtml.unescape(video_name.strip())
            channel_name_unescaped = ihtml.unescape(channel_name.strip())

            # ❗ Skip if video name is same as link
            if video_name_unescaped.strip() == video_link.strip():
                continue
            
            data.append({
                'video_name': video_name_unescaped,
                'video_link': video_link.strip(),
                'channel_name': channel_name_unescaped,
                'channel_link': channel_link.strip(),
                'watch_time': watch_time.strip()
            })

        # --- CASE 2: Minimal record with only video
        elif len(links) == 1 and time_match:
            # no channel means the video is no longer available
            continue

        else:
            # No usable record found, skip
            continue

        # Create DataFrame
        df = pd.DataFrame(data)

        # Save to CSV
        df.to_csv('data/watch-history.csv', index=False)

        print(f"Extracted {len(df)} entries and saved to watch-history.csv")
        return RedirectResponse(url="/", status_code=303)


@app.api_route("/api", methods=["GET", "POST"])
async def api_setup(request: Request):
    """Endpoint to enrich watch history data."""
    enrich_html_path = current_dir / "assets/api.html"
    config_path = current_dir / "cache" / "config.json"
    
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
        youtube_api_token = form_data.get("youtube-api-key")
        
        if youtube_api_token:
            cache_dir = current_dir / "cache"
            cache_dir.mkdir(exist_ok=True)
            config_path = cache_dir / "config.json"

            config_data = {"youtube-api-key": youtube_api_token}
            
            with config_path.open("w") as config_file:
                json.dump(config_data, config_file)

        if not youtube_api_token:
            return JSONResponse(content={"error": "YouTube API token is required"}, status_code=400)

        # Here you would add the logic to use the YouTube API token to enrich the watch history
        # For now, we'll just log the token and return a success message
        logger.info(f"Received YouTube API token: {youtube_api_token}")

        return RedirectResponse(url="/", status_code=303)
        


def get_assigned_port():
    import os
    return int(os.getenv("ASSIGNED_PORT", 8080))


async def main():
    task_box = asyncio.create_task(async_run_box())
    config = uvicorn.Config(app=app, host="0.0.0.0", port=get_assigned_port(), reload=True)
    server = uvicorn.Server(config)

    # Wait for both tasks (box and server) to complete
    await asyncio.gather(
        task_box,
        server.serve()
    )

if __name__ == "__main__":
    asyncio.run(main())
