import sys
import os
import subprocess
import requests
from supabase import create_client

song_id = sys.argv[1]
artist = sys.argv[2]
title = sys.argv[3]

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

if not RAPIDAPI_KEY:
    raise Exception("Missing RAPIDAPI_KEY secret in GitHub environment.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

raw_video = f"temp_{song_id}.mp4"
processed_video = f"{song_id}_2pc.mp4"

# 1. Search YouTube for Video ID (Flat search metadata only — never blocked)
search_query = f"{artist} {title} official music video"
print(f"🎵 Searching YouTube for ID: {search_query}...", flush=True)

cmd_search = [
    "yt-dlp", f"ytsearch1:{search_query}",
    "--flat-playlist",
    "--print", "id"
]
yt_id = subprocess.check_output(cmd_search).decode("utf-8").strip()
print(f"Found YouTube Video ID: {yt_id}", flush=True)

# 2. Request Direct Stream URL via RapidAPI
print("Requesting HD download URL from RapidAPI service...", flush=True)
api_url = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
headers = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "youtube-media-downloader.p.rapidapi.com"
}
params = {"videoId": yt_id}

resp = requests.get(api_url, headers=headers, params=params, timeout=15)
if resp.status_code != 200:
    raise Exception(f"RapidAPI request failed with status code {resp.status_code}: {resp.text}")

data = resp.json()

# Grab the highest resolution MP4 stream available
download_url = None
videos = data.get("videos", {}).get("items", [])

for v in videos:
    if v.get("hasAudio") and v.get("extension") == "mp4":
        download_url = v.get("url")
        break

if not download_url and videos:
    download_url = videos[0].get("url")

if not download_url:
    raise Exception("No valid download link returned by RapidAPI.")

# 3. Download the MP4 file
print("Downloading MP4 video stream...", flush=True)
dl_resp = requests.get(download_url, stream=True, timeout=60)
dl_resp.raise_for_status()

with open(raw_video, "wb") as f:
    for chunk in dl_resp.iter_content(chunk_size=1024 * 1024):
        if chunk:
            f.write(chunk)

# 4. Speed up Video & Audio by 2% via FFmpeg
cmd_ffmpeg = [
    "ffmpeg", "-y", "-i", raw_video,
    "-filter_complex", "[0:v]setpts=PTS/1.02[v];[0:a]atempo=1.02[a]",
    "-map", "[v]", "-map", "[a]",
    "-c:v", "libx264", "-crf", "20", "-preset", "faster",
    "-c:a", "aac", "-b:a", "192k",
    processed_video
]
print("Applying 2% speed boost with FFmpeg...", flush=True)
subprocess.run(cmd_ffmpeg, check=True)

if os.path.exists(raw_video):
    os.remove(raw_video)

# 5. Upload MP4 to Supabase Storage Bucket ('processed-videos')
bucket_path = f"videos/{processed_video}"
print("Uploading HD video to Supabase Storage...", flush=True)
with open(processed_video, 'rb') as f:
    supabase.storage.from_("processed-videos").upload(
        bucket_path, f, {"content-type": "video/mp4"}
    )

# 6. Save Public Video URL back to Supabase Table
public_url = supabase.storage.from_("processed-videos").get_public_url(bucket_path)
supabase.table("edge_library_log").update({"processed_video_url": public_url}).eq("song_id", song_id).execute()

print(f"✅ Successfully processed video: {public_url}", flush=True)
