"""Environment generator for shotcut v2 tasks.

Generates starter .mlt project files and placeholder mp4/mp3 media files for
each accepted task, then writes env_manifest.json per task.
"""
import json
import os
import subprocess
from pathlib import Path

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"

ROOT = Path("/Users/Mike/Desktop/syn_env/task_generator/tasks")


# ---------- helpers ----------

def run_ff(args, desc=""):
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + args
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed {desc}: {res.stderr[:500]}")


def make_video(path: Path, color: str, width: int, height: int, fps: int,
               duration: float = 1.0, with_audio: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if with_audio:
        args = [
            "-f", "lavfi", "-i",
            f"color=c={color}:s={width}x{height}:r={fps}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-t", str(duration), "-shortest",
            str(path),
        ]
    else:
        args = [
            "-f", "lavfi", "-i",
            f"color=c={color}:s={width}x{height}:r={fps}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            str(path),
        ]
    run_ff(args, desc=str(path))
    assert path.exists() and path.stat().st_size > 0


def make_audio(path: Path, freq: int = 440, duration: float = 1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
        "-c:a", "libmp3lame", str(path),
    ]
    run_ff(args, desc=str(path))
    assert path.exists() and path.stat().st_size > 0


# ---------- MLT project builders ----------

def mlt_empty(width, height, fps_num, fps_den=1, description=None):
    if description is None:
        description = f"{width}x{height} {fps_num}/{fps_den} fps"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7.14.0" producer="main_bin" root="/home/user">
  <profile description="{description}" width="{width}" height="{height}"
           progressive="1" sample_aspect_num="1" sample_aspect_den="1"
           display_aspect_num="16" display_aspect_den="9"
           frame_rate_num="{fps_num}" frame_rate_den="{fps_den}" colorspace="709"/>
  <playlist id="main_bin">
    <property name="shotcut:projectAudioChannels">2</property>
    <property name="shotcut:projectFolder">0</property>
  </playlist>
  <tractor id="tractor0" in="00:00:00.000" out="00:00:00.000">
    <property name="shotcut">1</property>
    <track producer="main_bin"/>
  </tractor>
</mlt>
"""


def mlt_with_clip_on_v1(width, height, fps_num, clip_resource, clip_name,
                       description=None, fps_den=1):
    """Build an .mlt with one chain entry on the V1 playlist + bin entry."""
    if description is None:
        description = f"{width}x{height} {fps_num}/{fps_den} fps"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7.14.0" producer="main_bin" root="/home/user">
  <profile description="{description}" width="{width}" height="{height}"
           progressive="1" sample_aspect_num="1" sample_aspect_den="1"
           display_aspect_num="16" display_aspect_den="9"
           frame_rate_num="{fps_num}" frame_rate_den="{fps_den}" colorspace="709"/>
  <chain id="chain0" out="00:00:01.000">
    <property name="length">00:00:02.000</property>
    <property name="resource">{clip_resource}</property>
    <property name="mlt_service">avformat</property>
    <property name="shotcut:caption">{clip_name}</property>
    <property name="shotcut:hash">deadbeefcafebabe</property>
  </chain>
  <playlist id="main_bin">
    <property name="shotcut:projectAudioChannels">2</property>
    <property name="shotcut:projectFolder">0</property>
    <entry producer="chain0" in="00:00:00.000" out="00:00:01.000"/>
  </playlist>
  <playlist id="playlist0">
    <property name="shotcut:video">1</property>
    <property name="shotcut:name">V1</property>
    <entry producer="chain0" in="00:00:00.000" out="00:00:01.000"/>
  </playlist>
  <tractor id="tractor0" in="00:00:00.000" out="00:00:01.000">
    <property name="shotcut">1</property>
    <track producer="main_bin"/>
    <track producer="playlist0"/>
  </tractor>
</mlt>
"""


# ---------- per-task builders ----------

def task_dir(task_id):
    d = ROOT / task_id / "env"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_manifest(task_id, files):
    manifest = {
        "task_id": task_id,
        "files": files,
    }
    (ROOT / task_id / "env_manifest.json").write_text(
        json.dumps(manifest, indent=2))


# 1. shotcut_v2_uhd_4k_project
def build_uhd_4k_project():
    tid = "shotcut_v2_uhd_4k_project"
    d = task_dir(tid)
    (d / "uhd_project.mlt").write_text(mlt_empty(1920, 1080, 30, description="HD 1080p 30 fps"))
    make_video(d / "drone.mp4", "navy", 320, 180, 30)
    write_manifest(tid, [
        {"filename": "uhd_project.mlt", "sandbox_path": "/home/user/Documents/uhd_project.mlt", "type": "mlt"},
        {"filename": "drone.mp4", "sandbox_path": "/home/user/Videos/drone.mp4", "type": "mp4"},
    ])


# 2. shotcut_v2_vertical_9x16_export
def build_vertical_export():
    tid = "shotcut_v2_vertical_9x16_export"
    d = task_dir(tid)
    # 9x16 portrait project needs different display aspect
    mlt = """<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7.14.0" producer="main_bin" root="/home/user">
  <profile description="Vertical 1080x1920 30 fps" width="1080" height="1920"
           progressive="1" sample_aspect_num="1" sample_aspect_den="1"
           display_aspect_num="9" display_aspect_den="16"
           frame_rate_num="30" frame_rate_den="1" colorspace="709"/>
  <chain id="chain0" out="00:00:01.000">
    <property name="length">00:00:02.000</property>
    <property name="resource">/home/user/Videos/reels_source.mp4</property>
    <property name="mlt_service">avformat</property>
    <property name="shotcut:caption">reels_source.mp4</property>
    <property name="shotcut:hash">a1b2c3d4e5f6</property>
  </chain>
  <playlist id="main_bin">
    <property name="shotcut:projectAudioChannels">2</property>
    <property name="shotcut:projectFolder">0</property>
    <entry producer="chain0" in="00:00:00.000" out="00:00:01.000"/>
  </playlist>
  <playlist id="playlist0">
    <property name="shotcut:video">1</property>
    <property name="shotcut:name">V1</property>
    <entry producer="chain0" in="00:00:00.000" out="00:00:01.000"/>
  </playlist>
  <tractor id="tractor0" in="00:00:00.000" out="00:00:01.000">
    <property name="shotcut">1</property>
    <track producer="main_bin"/>
    <track producer="playlist0"/>
  </tractor>
</mlt>
"""
    (d / "reels.mlt").write_text(mlt)
    # source video must match the vertical aspect
    make_video(d / "reels_source.mp4", "purple", 270, 480, 30, duration=1.0)
    write_manifest(tid, [
        {"filename": "reels.mlt", "sandbox_path": "/home/user/Documents/reels.mlt", "type": "mlt"},
        {"filename": "reels_source.mp4", "sandbox_path": "/home/user/Videos/reels_source.mp4", "type": "mp4"},
    ])


# 3. shotcut_v2_two_filters_sepia_contrast
def build_two_filters():
    tid = "shotcut_v2_two_filters_sepia_contrast"
    d = task_dir(tid)
    (d / "color_grade.mlt").write_text(
        mlt_with_clip_on_v1(1920, 1080, 30, "/home/user/Videos/landscape.mp4", "landscape.mp4",
                            description="HD 1080p 30 fps"))
    make_video(d / "landscape.mp4", "green", 320, 180, 30)
    write_manifest(tid, [
        {"filename": "color_grade.mlt", "sandbox_path": "/home/user/Documents/color_grade.mlt", "type": "mlt"},
        {"filename": "landscape.mp4", "sandbox_path": "/home/user/Videos/landscape.mp4", "type": "mp4"},
    ])


# 4. shotcut_v2_four_track_layered_composite
def build_four_track():
    tid = "shotcut_v2_four_track_layered_composite"
    d = task_dir(tid)
    (d / "layered.mlt").write_text(mlt_empty(1920, 1080, 30, description="HD 1080p 30 fps"))
    make_video(d / "bg.mp4", "blue", 320, 180, 30)
    make_video(d / "overlay.mp4", "red", 320, 180, 30)
    make_audio(d / "music.mp3", freq=440)
    make_audio(d / "voiceover.mp3", freq=660)
    write_manifest(tid, [
        {"filename": "layered.mlt", "sandbox_path": "/home/user/Documents/layered.mlt", "type": "mlt"},
        {"filename": "bg.mp4", "sandbox_path": "/home/user/Videos/bg.mp4", "type": "mp4"},
        {"filename": "overlay.mp4", "sandbox_path": "/home/user/Videos/overlay.mp4", "type": "mp4"},
        {"filename": "music.mp3", "sandbox_path": "/home/user/Music/music.mp3", "type": "mp3"},
        {"filename": "voiceover.mp3", "sandbox_path": "/home/user/Music/voiceover.mp3", "type": "mp3"},
    ])


# 5. shotcut_v2_default_profile_uhd_2160p_30
def build_default_profile_uhd():
    tid = "shotcut_v2_default_profile_uhd_2160p_30"
    d = task_dir(tid)
    (d / "prefs_uhd.mlt").write_text(mlt_empty(1280, 720, 30, description="HD 720p 30 fps"))
    write_manifest(tid, [
        {"filename": "prefs_uhd.mlt", "sandbox_path": "/home/user/Documents/prefs_uhd.mlt", "type": "mlt"},
    ])


# 6. shotcut_v2_export_audio_aac_mp4
def build_export_audio_aac():
    tid = "shotcut_v2_export_audio_aac_mp4"
    d = task_dir(tid)
    (d / "aac_export.mlt").write_text(
        mlt_with_clip_on_v1(1280, 720, 30, "/home/user/Videos/with_audio.mp4", "with_audio.mp4",
                            description="HD 720p 30 fps"))
    # Video WITH audio is essential
    make_video(d / "with_audio.mp4", "teal", 320, 180, 30, duration=2.0, with_audio=True)
    write_manifest(tid, [
        {"filename": "aac_export.mlt", "sandbox_path": "/home/user/Documents/aac_export.mlt", "type": "mlt"},
        {"filename": "with_audio.mp4", "sandbox_path": "/home/user/Videos/with_audio.mp4", "type": "mp4"},
    ])


# 7. shotcut_v2_five_clip_sequence
def build_five_clip_sequence():
    tid = "shotcut_v2_five_clip_sequence"
    d = task_dir(tid)
    (d / "montage.mlt").write_text(mlt_empty(1920, 1080, 30, description="HD 1080p 30 fps"))
    colors = ["red", "blue", "green", "yellow", "purple"]
    manifest_files = [{"filename": "montage.mlt", "sandbox_path": "/home/user/Documents/montage.mlt", "type": "mlt"}]
    for i, c in enumerate(colors, 1):
        name = f"clip{i}.mp4"
        make_video(d / name, c, 320, 180, 30, duration=1.0)
        manifest_files.append({"filename": name, "sandbox_path": f"/home/user/Videos/{name}", "type": "mp4"})
    write_manifest(tid, manifest_files)


# 8. shotcut_v2_transition_and_fadein_filter
def build_transition_and_filter():
    tid = "shotcut_v2_transition_and_fadein_filter"
    d = task_dir(tid)
    (d / "combo.mlt").write_text(mlt_empty(1920, 1080, 30, description="HD 1080p 30 fps"))
    make_video(d / "intro.mp4", "orange", 320, 180, 30, duration=2.0)
    make_video(d / "outro.mp4", "cyan", 320, 180, 30, duration=2.0)
    write_manifest(tid, [
        {"filename": "combo.mlt", "sandbox_path": "/home/user/Documents/combo.mlt", "type": "mlt"},
        {"filename": "intro.mp4", "sandbox_path": "/home/user/Videos/intro.mp4", "type": "mp4"},
        {"filename": "outro.mp4", "sandbox_path": "/home/user/Videos/outro.mp4", "type": "mp4"},
    ])


# 9. shotcut_v2_default_profile_dv_pal
def build_default_profile_pal():
    tid = "shotcut_v2_default_profile_dv_pal"
    d = task_dir(tid)
    (d / "pal_prefs.mlt").write_text(mlt_empty(1280, 720, 30, description="HD 720p 30 fps"))
    write_manifest(tid, [
        {"filename": "pal_prefs.mlt", "sandbox_path": "/home/user/Documents/pal_prefs.mlt", "type": "mlt"},
    ])


# 10. shotcut_v2_crop_filter_on_clip
def build_crop_filter():
    tid = "shotcut_v2_crop_filter_on_clip"
    d = task_dir(tid)
    (d / "crop_me.mlt").write_text(
        mlt_with_clip_on_v1(1920, 1080, 30, "/home/user/Videos/wide_shot.mp4", "wide_shot.mp4",
                            description="HD 1080p 30 fps"))
    make_video(d / "wide_shot.mp4", "maroon", 320, 180, 30)
    write_manifest(tid, [
        {"filename": "crop_me.mlt", "sandbox_path": "/home/user/Documents/crop_me.mlt", "type": "mlt"},
        {"filename": "wide_shot.mp4", "sandbox_path": "/home/user/Videos/wide_shot.mp4", "type": "mp4"},
    ])


BUILDERS = [
    build_uhd_4k_project,
    build_vertical_export,
    build_two_filters,
    build_four_track,
    build_default_profile_uhd,
    build_export_audio_aac,
    build_five_clip_sequence,
    build_transition_and_filter,
    build_default_profile_pal,
    build_crop_filter,
]


def verify_all():
    """Parse each generated .mlt and assert structure is well-formed."""
    import xml.etree.ElementTree as ET
    for bf in BUILDERS:
        # derive tid from function name (strip "build_")
        pass
    # Instead, walk the tasks dirs we just wrote
    for task_id_dir in ROOT.glob("shotcut_v2_*"):
        env = task_id_dir / "env"
        for mlt in env.glob("*.mlt"):
            tree = ET.parse(mlt)
            root = tree.getroot()
            assert root.tag == "mlt", f"{mlt}: bad root"
            prof = root.find("profile")
            assert prof is not None, f"{mlt}: no profile"
            print(f"OK  {mlt.relative_to(ROOT)}  profile={prof.get('width')}x{prof.get('height')}")
        for mp4 in env.glob("*.mp4"):
            assert mp4.stat().st_size > 0
            print(f"OK  {mp4.relative_to(ROOT)}  size={mp4.stat().st_size}")
        for mp3 in env.glob("*.mp3"):
            assert mp3.stat().st_size > 0
            print(f"OK  {mp3.relative_to(ROOT)}  size={mp3.stat().st_size}")


if __name__ == "__main__":
    for bf in BUILDERS:
        print(f">>> {bf.__name__}")
        bf()
    print("\n-- verification --")
    verify_all()
    print("\nAll done.")
