import json
import platform
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont


def create_share_image(year, app_data_dir, output_path):
    with open(
        app_data_dir / "cache" / f"youtube-wrapped-{year}.json", encoding="utf-8"
    ) as f:
        data = json.loads(f.read())

    year = str(data["year"])
    formatted_minutes = f"{data['total_minutes']:,}"
    total_days = str(data["total_days"])
    top_video = data["top_videos"][0]

    top_video_thumb = data["top_videos_thumbs"][0]

    top_channels = data["top_channels"][0:3]

    top_day_date_day_name = data["top_day_date_day_name"]
    top_day_date_day = data["top_day_date_day"]
    top_day_date_month = data["top_day_date_month"]
    top_day_date_year = data["top_day_date_year"]
    top_day_minutes = data["top_day_minutes"]

    response = requests.get(top_video_thumb)
    thumbnail = Image.open(BytesIO(response.content)).convert("RGB")

    # Step 2: Resize it to fit the 120x80 placeholder box
    thumbnail = thumbnail.resize((120, 80))

    def wrap_text(text, font, max_width, draw):
        lines = []
        words = text.split()
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
            if text_width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    # Step 1: Create a square image
    size = 600
    bg_color = (24, 24, 24)  # dark background
    img = Image.new("RGB", (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    # Step 2: Load fonts
    # You can use any .ttf font path here
    if platform.system() == "Darwin":  # macOS
        font_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    elif platform.system() == "Windows":
        font_path = "C:\\Windows\\Fonts\\arialbd.ttf"
    else:  # Assume Linux
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    title_font = ImageFont.truetype(font_path, 48)
    year_font = ImageFont.truetype(font_path, 36)
    stat_label_font = ImageFont.truetype(font_path, 16)
    stat_value_font = ImageFont.truetype(font_path, 32)
    video_title_font = ImageFont.truetype(font_path, 16)
    more_text_font = ImageFont.truetype(font_path, 18)
    syftbox_font = ImageFont.truetype(font_path, 14)

    # Step 3: Draw red accent bar
    draw.rectangle([(592, 0), (600, 600)], fill=(255, 0, 0))

    # Step 4: Add header
    draw.text((40, 40), "YouTube Wrapped", font=title_font, fill=(255, 0, 0))
    draw.text((40, 100), year, font=year_font, fill=(255, 0, 0))

    # Step 5: Add stats
    draw.text((40, 160), "Minutes Watched", font=stat_label_font, fill=(170, 170, 170))
    draw.text((40, 180), formatted_minutes, font=stat_value_font, fill=(255, 255, 255))

    draw.text((300, 160), "Days Watched", font=stat_label_font, fill=(170, 170, 170))
    draw.text((300, 180), total_days, font=stat_value_font, fill=(255, 255, 255))

    # Construct date string
    top_day_str = f"{top_day_date_day_name}, {top_day_date_day} {top_day_date_month}/{top_day_date_year}"
    watched_msg = f"Most watched day: {top_day_str} ({top_day_minutes:,} minutes)"

    # Draw it near the logo
    draw.text((40, 240), watched_msg, font=syftbox_font, fill=(180, 180, 180))

    video_y = 290
    # Max width in pixels you want for each line (adjust to your layout)
    max_width = 400

    # Wrap it
    lines = wrap_text(top_video, video_title_font, max_width, draw)

    draw.text((40, video_y), "Top Video", font=stat_label_font, fill=(255, 0, 0))

    # Paste thumbnail lower
    img.paste(thumbnail, (40, video_y + 30))

    # Draw wrapped title lines lower
    x, y = 170, video_y + 40
    line_height = 25
    for line in lines[:3]:
        draw.text((x, y), line, font=video_title_font, fill=(255, 255, 255))
        y += line_height

    # Starting coordinates
    x_channel = 40
    y_channel = 430
    draw.text(
        (x_channel, y_channel), "Top Channels", font=stat_label_font, fill=(255, 0, 0)
    )
    y_channel += 22

    for i, channel in enumerate(top_channels[:3]):
        draw.text(
            (x_channel, y_channel + i * 18),
            f"{i + 1}. {channel}",
            font=syftbox_font,
            fill=(255, 255, 255),
        )

    logo = Image.open("./assets/images/mwsyftbox_white_on.png").convert("RGBA")

    # Optional: Resize the logo if it's too big
    logo = logo.resize((343 // 2, 131 // 2))  # Adjust size as needed

    # Paste the logo onto your canvas image
    # (400, 550) is the top-left corner where it will be placed
    img.paste(
        logo, (400, 500), logo
    )  # Use logo as its own mask to preserve transparency

    # Align logo top-right, level with the text "Youtube Wrapped"
    yt_width, yt_height = 60, 40
    yt_x = size - yt_width - 60  # 40px padding from right
    yt_y = 48  # same as title top padding

    # Red pill background
    draw.rounded_rectangle(
        [(yt_x, yt_y), (yt_x + yt_width, yt_y + yt_height)], radius=10, fill=(255, 0, 0)
    )

    # White triangle play icon, centered
    triangle = [
        (yt_x + 18, yt_y + 10),
        (yt_x + 18, yt_y + yt_height - 10),
        (yt_x + yt_width - 15, yt_y + yt_height // 2),
    ]
    draw.polygon(triangle, fill="white")

    # Step 7: and more...
    draw.text((40, 540), "and more...", font=more_text_font, fill=(170, 170, 170))

    # Step 10: Save
    img.save(output_path)
