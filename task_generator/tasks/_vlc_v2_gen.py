#!/usr/bin/env python3
"""Generate env files for vlc_v2 tasks using ffmpeg (imageio_ffmpeg)."""
import os
import subprocess
import sys
import json

FFMPEG = "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"
FFPROBE_HACK = None  # we'll use ffmpeg -i and parse stderr for validation

BASE = "/Users/Mike/Desktop/syn_env/task_generator/tasks"

def run(cmd, check=True):
    print(" ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if check and res.returncode != 0:
        print("STDERR:", res.stderr[-2000:])
        raise RuntimeError(f"ffmpeg failed: {cmd}")
    return res

def make_video(path, duration, width=640, height=480, with_audio=True, vcodec="libx264", acodec="aac", container=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    inputs = [
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=25",
    ]
    if with_audio:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
    out = [
        "-c:v", vcodec, "-pix_fmt", "yuv420p",
    ]
    if with_audio:
        out += ["-c:a", acodec, "-shortest"]
    cmd = [FFMPEG, "-y", *inputs, *out, path]
    run(cmd)

def make_mp3(path, duration):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    cmd = [FFMPEG, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
           "-c:a", "libmp3lame", "-b:a", "128k", path]
    run(cmd)

def make_mkv(path, duration):
    make_video(path, duration, width=640, height=480, with_audio=True, vcodec="libx264", acodec="aac")

def probe_duration(path):
    res = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    # Parse "Duration: HH:MM:SS.xx"
    for line in res.stderr.split("\n"):
        if "Duration:" in line:
            dur_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = dur_str.split(":")
            return int(h)*3600 + int(m)*60 + float(s)
    return None

def probe_format(path):
    res = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True)
    # Extract Input #0, <format>, from stderr
    for line in res.stderr.split("\n"):
        if line.startswith("Input #0,"):
            fmt = line.split("Input #0,")[1].split(",")[0].strip()
            return fmt
    return None

TASKS = {
    "vlc_convert_mp4_to_hd_mp4_resolution": [
        {"path": "src_hd.mp4", "gen": lambda p: make_video(p, 20, 1920, 1080, True)},
    ],
    "vlc_convert_audio_extract_wav": [
        {"path": "music_clip.mp4", "gen": lambda p: make_video(p, 15, 640, 480, True)},
    ],
    "vlc_repeat_single_track": [
        {"path": "loopme.mp4", "gen": lambda p: make_video(p, 12, 640, 480, True)},
    ],
    "vlc_combo_loop_volume_fullscreen": [
        {"path": "combo.mp4", "gen": lambda p: make_video(p, 25, 640, 480, True)},
    ],
    "vlc_seek_near_end": [
        {"path": "long_clip.mp4", "gen": lambda p: make_video(p, 60, 640, 480, True)},
    ],
    "vlc_convert_wav_from_mp3_source": [
        {"path": "source_audio.mp3", "gen": lambda p: make_mp3(p, 10)},
    ],
    "vlc_playlist_advance_to_second": [
        {"path": "track_a.mp4", "gen": lambda p: make_video(p, 15, 640, 480, True)},
        {"path": "track_b.mp4", "gen": lambda p: make_video(p, 15, 640, 480, True)},
    ],
    "vlc_convert_mp4_to_ogg_audio": [
        {"path": "ogg_src.mp4", "gen": lambda p: make_video(p, 15, 640, 480, True)},
    ],
    "vlc_high_volume_150": [
        {"path": "amp.mp4", "gen": lambda p: make_video(p, 10, 640, 480, True)},
    ],
    "vlc_convert_mkv_to_webm": [
        {"path": "src.mkv", "gen": lambda p: make_mkv(p, 20)},
    ],
}

def main():
    for task_id, files in TASKS.items():
        env_dir = os.path.join(BASE, task_id, "env")
        os.makedirs(env_dir, exist_ok=True)
        for f in files:
            full_path = os.path.join(env_dir, f["path"])
            f["gen"](full_path)
            # Verify
            assert os.path.exists(full_path), f"Missing {full_path}"
            assert os.path.getsize(full_path) > 1000, f"Too small {full_path}"
            dur = probe_duration(full_path)
            fmt = probe_format(full_path)
            print(f"  OK {f['path']}: {os.path.getsize(full_path)}B dur={dur} fmt={fmt}")

if __name__ == "__main__":
    main()
