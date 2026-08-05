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

search_query = f"{artist} {title} official music video"
print(f"🎵 Downloading HD video for: {artist} - {title}...", flush=True)

# 1. Download HD video directly with yt-dlp using web/mobile fallbacks
cmd_dl = [
    "yt-dlp", f"ytsearch1:{search_query}",
    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "--merge-output-format", "mp4",
    "--extractor-args", "youtube:player_client=web,mweb,android",
    "-o", raw_video
]

proc = subprocess.Popen(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

for line in iter(proc.stdout.readline, ''):
    print(line, end='', flush=True)

proc.stdout.close()
return_code = proc.wait()

if return_code != 0:
    raise subprocess.CalledProcessError(return_code, cmd_dl)

# 2. Speed up Video & Audio by 2% via FFmpeg
cmd_ffmpeg = [
    "ffmpeg", "-y", "-i", raw_video,
    "-filter_complex", "[0:v]setpts=PTS/1.02[v];[0:a]atempo=1.02[a]",
    "-map", "[v]", "-map", "[a]",
    "-c:v", "libx264", "-crf", "20", "-preset", "faster",
    "-c:a", "aac", "-b:a", "192k",
    processed_video
]
print("Applying 2% speed boost...", flush=True)
subprocess.run(cmd_ffmpeg, check=True)

if os.path.exists(raw_video):
    os.remove(raw_video)

# 3. Upload MP4 to Supabase Storage Bucket ('processed-videos')
bucket_path = f"videos/{processed_video}"
print("Uploading HD video to Supabase Storage...", flush=True)
with open(processed_video, 'rb') as f:
    supabase.storage.from_("processed-videos").upload(
        bucket_path, f, {"content-type": "video/mp4"}
    )

# 4. Save Public Video URL back to Supabase Table
public_url = supabase.storage.from_("processed-videos").get_public_url(bucket_path)
supabase.table("edge_library_log").update({"processed_video_url": public_url}).eq("song_id", song_id).execute()

print(f"✅ Successfully processed video: {public_url}", flush=True)
