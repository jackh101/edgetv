import sys
import os
import re
import subprocess
from supabase import create_client

song_id = sys.argv[1]
artist = sys.argv[2]
title = sys.argv[3]

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
YOUTUBE_COOKIES_RAW = os.environ.get("YOUTUBE_COOKIES", "").strip()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

raw_video = f"temp_{song_id}.mp4"
processed_video = f"{song_id}_2pc.mp4"
cookie_file = "cookies.txt"

has_cookies = False
if YOUTUBE_COOKIES_RAW:
    print("🔑 Parsing YOUTUBE_COOKIES secret...", flush=True)

    if "# Netscape HTTP Cookie File" in YOUTUBE_COOKIES_RAW:
        with open(cookie_file, "w") as f:
            f.write(YOUTUBE_COOKIES_RAW)
        has_cookies = True
    else:
        flat_text = YOUTUBE_COOKIES_RAW.replace('\\\n', ' ').replace('\n', ' ')
        match = re.search(r"(?:-h\s+['\"]?cookie:\s*|cookie:\s*)([^'\"]+)", flat_text, re.IGNORECASE)
        cookie_str = match.group(1).strip() if match else flat_text

        lines = ["# Netscape HTTP Cookie File\n"]
        count = 0
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                parts = pair.split("=", 1)
                k, v = parts[0].strip(), parts[1].strip()
                if k and v and not k.startswith("-") and " " not in k and not k.lower().startswith("sec-"):
                    lines.append(f".youtube.com\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
                    count += 1

        if count > 0:
            with open(cookie_file, "w") as f:
                f.writelines(lines)
            has_cookies = True
            print(f"✅ Extracted {count} authentication cookies.", flush=True)

search_query = f"{artist} {title} official music video"
print(f"🎵 Searching & Downloading HD video for: {artist} - {title}...", flush=True)

cmd_dl = [
    "yt-dlp",
    "-v",
    f"ytsearch1:{search_query}",
    "-f", "bestvideo*[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    "-S", "res:1080,codec:h264",
    "--merge-output-format", "mp4",
    "--force-ipv4",
    "--retries", "25",
    "--
