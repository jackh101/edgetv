import sys
import os
import subprocess
from supabase import create_client

song_id = sys.argv[1]
artist = sys.argv[2]
title = sys.argv[3]

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

raw_video = f"temp_{song_id}.mp4"
processed_video = f"{song_id}_2pc.mp4"

# Client rotation strategy to bypass YouTube cloud IP bot detection
clients = [
    "tv_downgraded,web_creator",
    "android_vr,web",
    "tv,web_embedded"
]

download_success = False
query = f"ytsearch1:{artist} {title} official music video"

for client in clients:
    print(f"Downloading HD video for: {artist} - {title} (Strategy: {client})...")
    cmd_dl = [
        "yt-dlp", query,
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--extractor-args", f"youtube:player_client={client}",
        "-o", raw_video
    ]
    res = subprocess.run(cmd_dl)
    if res.returncode == 0 and os.path.exists(raw_video):
        download_success = True
        break

if not download_success:
    raise Exception("Failed to download video: YouTube blocked all client strategies.")

# 2. Speed up Video & Audio by 2%
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

# 3. Upload MP4 to Supabase Storage Bucket ('processed-videos')
bucket_path = f"videos/{processed_video}"
print("Uploading HD video to Supabase Storage...")
with open(processed_video, 'rb') as f:
    supabase.storage.from_("processed-videos").upload(
        bucket_path, f, {"content-type": "video/mp4"}
    )

# 4. Save Public Video URL back to Supabase Table
public_url = supabase.storage.from_("processed-videos").get_public_url(bucket_path)
supabase.table("edge_library_log").update({"processed_video_url": public_url}).eq("song_id", song_id).execute()

print(f"Successfully processed video: {public_url}")
