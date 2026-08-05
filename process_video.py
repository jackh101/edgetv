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
    
    # Case A: If pasted as a native Netscape cookies.txt file directly
    if "# Netscape HTTP Cookie File" in YOUTUBE_COOKIES_RAW:
        with open(cookie_file, "w") as f:
            f.write(YOUTUBE_COOKIES_RAW)
        has_cookies = True
    else:
        # Case B: User pasted a cURL command or raw Cookie header (potentially multi-line)
        flat_text = YOUTUBE_COOKIES_RAW.replace('\\\n', ' ').replace('\n', ' ')
        
        # Extract the Cookie header value
        match = re.search(r"(?:-h\s+['\"]?cookie:\s*|cookie:\s*)([^'\"]+)", flat_text, re.IGNORECASE)
        cookie_str = match.group(1).strip() if match else flat_text
        
        lines = ["# Netscape HTTP Cookie File\n"]
        count = 0
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                parts = pair.split("=", 1)
                k, v = parts[0].strip(), parts[1].strip()
                # Ignore cURL flags and non-cookie headers
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
    "yt-dlp", f"ytsearch1:{search_query}",
    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "--merge-output-format", "mp4",
    "-o", raw_video
]

if has_cookies:
    cmd_dl.extend(["--cookies", cookie_file])

proc = subprocess.Popen(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

for line in iter(proc.stdout.readline, ''):
    print(line, end='', flush=True)

proc.stdout.close()
return_code = proc.wait()

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

print(f"🎉 Successfully processed video: {public_url}", flush=True)
