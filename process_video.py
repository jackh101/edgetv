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

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

raw_video = f"temp_{song_id}.mp4"
processed_video = f"{song_id}_2pc.mp4"

# 1. Search YouTube for Video ID (--flat-playlist gets ID without triggering bot checks)
search_query = f"{artist} {title} official music video"
print(f"🎵 Searching YouTube for: {search_query}...")

cmd_search = [
    "yt-dlp", f"ytsearch1:{search_query}",
    "--flat-playlist",
    "--print", "id"
]
yt_id = subprocess.check_output(cmd_search).decode("utf-8").strip()
youtube_url = f"https://www.youtube.com/watch?v={yt_id}"
print(f"Found YouTube URL: {youtube_url}")

# 2. Fetch direct MP4 download link via Cobalt API (Bypasses YouTube IP blocks)
print("Bypassing YouTube IP blocks via Cobalt API...")
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}
payload = {
    "url": youtube_url,
    "videoQuality": "1080",
    "youtubeVideoContainer": "mp4"
}

# Public Cobalt instances for fallback reliability
instances = [
    "https://api.cobalt.tools/",
    "https://cobalt-api.kwiatek.xyz/",
    "https://api.cobalt.crush.org.za/"
]

download_url = None
for api_url in instances:
    try:
        res = requests.post(api_url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            data = res.json()
            download_url = data.get("url")
            if download_url:
                print(f"Successfully fetched stream from {api_url}")
                break
    except Exception as e:
        print(f"Instance {api_url} busy/skipped: {e}")

if not download_url:
    raise Exception("Failed to retrieve download link from Cobalt API.")

# 3. Stream HD MP4 file to disk
print("Downloading HD video file...")
with requests.get(download_url, stream=True) as r:
    r.raise_for_status()
    with open(raw_video, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
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
print("Applying 2% speed boost...")
subprocess.run(cmd_ffmpeg, check=True)

if os.path.exists(raw_video):
    os.remove(raw_video)

# 5. Upload MP4 to Supabase Storage Bucket ('processed-videos')
bucket_path = f"videos/{processed_video}"
print("Uploading HD video to Supabase Storage...")
with open(processed_video, 'rb') as f:
    supabase.storage.from_("processed-videos").upload(
        bucket_path, f, {"content-type": "video/mp4"}
    )

# 6. Save Public Video URL back to Supabase Table
public_url = supabase.storage.from_("processed-videos").get_public_url(bucket_path)
supabase.table("edge_library_log").update({"processed_video_url": public_url}).eq("song_id", song_id).execute()

print(f"✅ Successfully processed video: {public_url}")
