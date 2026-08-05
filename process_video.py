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
YOUTUBE_COOKIES_RAW = os.environ.get("YOUTUBE_COOKIES", "")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

raw_video = f"temp_{song_id}.mp4"
processed_video = f"{song_id}_2pc.mp4"
cookie_file = "cookies.txt"

# Smart Parser: Converts raw cURL string or header text into a Netscape cookie file
def prepare_cookie_file(raw_text, filepath):
    if not raw_text:
        return False
    
    # Extract cookies if pasted as a full cURL command
    match = re.search(r"cookie:\s*([^'\"]+)", raw_text, re.IGNORECASE)
    cookie_str = match.group(1) if match else raw_text

    lines = ["# Netscape HTTP Cookie File\n"]
    for pair in cookie_str.split(";"):
        if "=" in pair:
            parts = pair.strip().split("=", 1)
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()
                lines.append(f".youtube.com\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
    
    if len(lines) > 1:
        with open(filepath, "w") as f:
            f.writelines(lines)
        return True
    return False

has_cookies = prepare_cookie_file(YOUTUBE_COOKIES_RAW, cookie_file)

search_query = f"{artist} {title} official music video"
print(f"🎵 Searching & Downloading HD video for: {artist} - {title}...", flush=True)

cmd_dl = [
    "yt-dlp", f"ytsearch1:{search_query}",
    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "--merge-output-format", "mp4",
    "-o", raw_video
]

if has_cookies:
    print("🔑 Authenticating with YouTube session cookies...", flush=True)
    cmd_dl.extend(["--cookies", cookie_file])

proc = subprocess.Popen(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

for line in iter(proc.stdout.readline, ''):
    print(line, end='', flush=True)

proc.stdout.close()
return_code = proc.wait()

# Clean up cookie file from memory
if os.path.exists(cookie_file):
    os.remove(cookie_file)

if return_code != 0:
    raise subprocess.CalledProcessError(return_code, cmd_dl)

# Speed up Video & Audio by 2% via FFmpeg
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

# Upload MP4 to Supabase Storage Bucket ('processed-videos')
bucket_path = f"videos/{processed_video}"
print("Uploading HD video to Supabase Storage...", flush=True)
with open(processed_video, 'rb') as f:
    supabase.storage.from_("processed-videos").upload(
        bucket_path, f, {"content-type": "video/mp4"}
    )

# Save Public Video URL back to Supabase Table
public_url = supabase.storage.from_("processed-videos").get_public_url(bucket_path)
supabase.table("edge_library_log").update({"processed_video_url": public_url}).eq("song_id", song_id).execute()

print(f"✅ Successfully processed video: {public_url}", flush=True)
