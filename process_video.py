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

# 1. Search YouTube for Video ID (Flat search never triggers bot checks)
search_query = f"{artist} {title} official music video"
print(f"🎵 Searching YouTube for: {search_query}...")

cmd_search = [
    "yt-dlp", f"ytsearch1:{search_query}",
    "--flat-playlist",
    "--print", "id"
]
yt_id = subprocess.check_output(cmd_search).decode("utf-8").strip()
print(f"Found YouTube Video ID: {yt_id}")

# 2. Fetch direct media streams via Piped Proxy API (No cookies required!)
piped_instances = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.leptons.xyz",
    "https://api.piped.yt",
    "https://pipedapi.privacy.com.de"
]

video_url = None
audio_url = None

for base in piped_instances:
    try:
        print(f"Fetching stream via proxy {base}...")
        res = requests.get(f"{base}/streams/{yt_id}", timeout=10)
        if res.status_code == 200:
            data = res.json()
            v_streams = data.get("videoStreams", [])
            a_streams = data.get("audioStreams", [])
            
            # Find progressive video stream (video + audio in one stream)
            combined = [s for s in v_streams if not s.get("videoOnly", True)]
            if combined:
                video_url = combined[0]["url"]
                print(f"✅ Secured combined stream from {base}")
                break
            elif v_streams and a_streams:
                video_url = v_streams[0]["url"]
                audio_url = a_streams[0]["url"]
                print(f"✅ Secured video & audio streams from {base}")
                break
    except Exception as e:
        print(f"Proxy instance {base} skipped: {e}")

if not video_url:
    raise Exception("Unable to reach Piped proxy network for video stream.")

# 3. Stream & apply 2% speed boost directly with FFmpeg
print("Applying 2% speed boost with FFmpeg...")
if audio_url:
    cmd_ffmpeg = [
        "ffmpeg", "-y",
        "-i", video_url,
        "-i", audio_url,
        "-filter_complex", "[0:v]setpts=PTS/1.02[v];[1:a]atempo=1.02[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "20", "-preset", "faster",
        "-c:a", "aac", "-b:a", "192k",
        processed_video
    ]
else:
    cmd_ffmpeg = [
        "ffmpeg", "-y",
        "-i", video_url,
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
