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

processed_video = f"{song_id}_2pc.mp4"

# 1. Search YouTube for Video ID (Flat search only fetches text metadata and is never blocked)
search_query = f"{artist} {title} official music video"
print(f"🎵 Searching YouTube for ID: {search_query}...")

cmd_search = [
    "yt-dlp", f"ytsearch1:{search_query}",
    "--flat-playlist",
    "--print", "id"
]
yt_id = subprocess.check_output(cmd_search).decode("utf-8").strip()
print(f"Found YouTube Video ID: {yt_id}")

# 2. Fetch official live proxy list dynamically from the Invidious registry
print("Fetching active proxy list from Invidious registry...")
instance_list_url = "https://api.invidious.io/instances.json?sort_by=health"
resp = requests.get(instance_list_url, timeout=10)
instances_data = resp.json()

# Filter for active HTTPS instances with API enabled
live_instances = []
for item in instances_data:
    domain = item[0]
    info = item[1]
    if info.get("type") == "https" and info.get("api") == True:
        live_instances.append(f"https://{domain}")

print(f"Found {len(live_instances)} active proxy instances.")

video_stream_url = None

# Loop through live proxies until one returns a working video stream
for base_url in live_instances:
    try:
        api_endpoint = f"{base_url}/api/v1/videos/{yt_id}"
        print(f"Testing live proxy: {base_url}...")
        r = requests.get(api_endpoint, timeout=8)
        if r.status_code == 200:
            data = r.json()
            format_streams = data.get("formatStreams", [])
            
            if format_streams:
                video_stream_url = format_streams[0].get("url")
                if video_stream_url:
                    print(f"✅ Secured stream from {base_url}")
                    break
    except Exception as e:
        print(f"Proxy {base_url} busy/skipped: {e}")

if not video_stream_url:
    raise Exception("Could not retrieve stream from any live proxy instances.")

# 3. Stream & apply 2% speed boost directly with FFmpeg
print("Applying 2% speed boost with FFmpeg...")
cmd_ffmpeg = [
    "ffmpeg", "-y",
    "-i", video_stream_url,
    "-filter_complex", "[0:v]setpts=PTS/1.02[v];[0:a]atempo=1.02[a]",
    "-map", "[v]", "-map", "[a]",
    "-c:v", "libx264", "-crf", "20", "-preset", "faster",
    "-c:a", "aac", "-b:a", "192k",
    processed_video
]

subprocess.run(cmd_ffmpeg, check=True)

# 4. Upload MP4 to Supabase Storage Bucket ('processed-videos')
bucket_path = f"videos/{processed_video}"
print("Uploading HD video to Supabase Storage...")
with open(processed_video, 'rb') as f:
    supabase.storage.from_("processed-videos").upload(
        bucket_path, f, {"content-type": "video/mp4"}
    )

# 5. Save Public Video URL back to Supabase Table
public_url = supabase.storage.from_("processed-videos").get_public_url(bucket_path)
supabase.table("edge_library_log").update({"processed_video_url": public_url}).eq("song_id", song_id).execute()

print(f"🎉 Successfully processed video: {public_url}")
