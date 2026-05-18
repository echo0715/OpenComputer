"""Generate env files for obs v2 tasks (Stage 3).

Creates:
  - Pre-built OBS scene collection JSON files for tasks that need a starting state
  - Small PNG images for image-source tasks
  - env_manifest.json for each task
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TASKS_DIR = Path("/Users/Mike/Desktop/syn_env/task_generator/tasks")


def make_png(path: Path, size=(640, 360), color=(30, 60, 120), label: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    if label:
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(
                "/System/Library/Fonts/Helvetica.ttc", 48
            )
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((size[0] - tw) / 2, (size[1] - th) / 2),
            label,
            font=font,
            fill=(240, 240, 240),
        )
    img.save(path, "PNG")


def make_scene_item(name: str, visible: bool = True) -> dict:
    return {
        "name": name,
        "visible": visible,
        "locked": False,
        "pos": {"x": 0.0, "y": 0.0},
        "rot": 0.0,
        "scale": {"x": 1.0, "y": 1.0},
        "align": 5,
        "bounds": {"x": 0.0, "y": 0.0},
        "bounds_align": 0,
        "bounds_type": 0,
    }


def make_source_def(name: str, versioned_id: str = "xshm_input") -> dict:
    return {
        "name": name,
        "id": versioned_id,
        "versioned_id": versioned_id,
        "settings": {},
        "enabled": True,
        "mute": False,
        "volume": 1.0,
    }


def build_collection(
    scene_name_to_items: dict[str, list[dict]],
    top_level_sources: list[dict] | None = None,
    current_scene: str | None = None,
) -> dict:
    """Build an OBS-compatible scene collection JSON.

    scene_name_to_items: ordered map scene_name -> list of items returned by make_scene_item.
    top_level_sources: optional source defs (non-scene). Inferred from items by default.
    """
    scene_order = [{"name": s} for s in scene_name_to_items.keys()]

    sources = []
    # Add source defs for every item seen (simple xshm_input placeholder)
    seen_source_defs = set()
    if top_level_sources:
        for s in top_level_sources:
            sources.append(s)
            seen_source_defs.add(s["name"])

    for scene_name, items in scene_name_to_items.items():
        for it in items:
            if it["name"] not in seen_source_defs:
                sources.append(make_source_def(it["name"]))
                seen_source_defs.add(it["name"])

    # Add each scene as a source of type "scene"
    for scene_name, items in scene_name_to_items.items():
        sources.append(
            {
                "name": scene_name,
                "id": "scene",
                "versioned_id": "scene",
                "settings": {"items": items},
                "enabled": True,
                "mute": False,
            }
        )

    return {
        "current_scene": current_scene or next(iter(scene_name_to_items.keys())),
        "scene_order": scene_order,
        "sources": sources,
        "name": "Untitled",
    }


def write_env(task_id: str, files: list[dict]) -> None:
    env_dir = TASKS_DIR / task_id / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"task_id": task_id, "files": files}
    (TASKS_DIR / task_id / "env_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )


def save_collection(task_id: str, collection: dict) -> None:
    env_dir = TASKS_DIR / task_id / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "scene_collection.json").write_text(
        json.dumps(collection, indent=2)
    )


# ---------------------------------------------------------------------------
# Task 1: obs_prune_crowded_scene
#   One scene 'Master' with 8 sources.
# ---------------------------------------------------------------------------
def gen_prune_crowded_scene() -> None:
    tid = "obs_prune_crowded_scene"
    items = [
        make_scene_item("Primary Cam"),
        make_scene_item("Secondary Cam"),
        make_scene_item("Desktop"),
        make_scene_item("Chat Overlay"),
        make_scene_item("BRB Image"),
        make_scene_item("Stinger Video"),
        make_scene_item("Logo"),
        make_scene_item("Audio Meter"),
    ]
    col = build_collection({"Master": items})
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 2: obs_hide_but_keep_sources
#   One scene 'Live' with 6 visible sources.
# ---------------------------------------------------------------------------
def gen_hide_but_keep_sources() -> None:
    tid = "obs_hide_but_keep_sources"
    names = ["Camera A", "Camera B", "Screen", "Title Text", "Logo", "Alert Box"]
    items = [make_scene_item(n) for n in names]
    col = build_collection({"Live": items})
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 3: obs_delete_unused_scenes
#   6 scenes each with one distinctive placeholder source.
# ---------------------------------------------------------------------------
def gen_delete_unused_scenes() -> None:
    tid = "obs_delete_unused_scenes"
    mapping = {
        "Intro": [make_scene_item("Intro Card")],
        "Main": [make_scene_item("Main Cam")],
        "BRB": [make_scene_item("BRB Text")],
        "Outro": [make_scene_item("Outro Roll")],
        "Debug": [make_scene_item("Debug Console")],
        "Archive": [make_scene_item("Archive Stamp")],
    }
    col = build_collection(mapping)
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 4: obs_news_broadcast_layout
#   Fresh build. Needs news_logo.png and weather_map.png.
# ---------------------------------------------------------------------------
def gen_news_broadcast_layout() -> None:
    tid = "obs_news_broadcast_layout"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    make_png(env_dir / "news_logo.png", size=(512, 256), color=(180, 20, 20), label="EVN NEWS")
    make_png(
        env_dir / "weather_map.png",
        size=(800, 500),
        color=(40, 90, 140),
        label="Weather Map",
    )
    write_env(
        tid,
        [
            {"filename": "news_logo.png", "sandbox_path": "/home/user/Pictures/news_logo.png", "type": "png"},
            {"filename": "weather_map.png", "sandbox_path": "/home/user/Pictures/weather_map.png", "type": "png"},
        ],
    )


# ---------------------------------------------------------------------------
# Task 5: obs_consolidate_into_single_scene
#   3 starting scenes each with one named source.
# ---------------------------------------------------------------------------
def gen_consolidate_into_single_scene() -> None:
    tid = "obs_consolidate_into_single_scene"
    mapping = {
        "Cam A": [make_scene_item("Webcam A")],
        "Cam B": [make_scene_item("Webcam B")],
        "Graphics": [make_scene_item("Lower Third")],
    }
    col = build_collection(mapping)
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 6: obs_browser_source_web_overlay
#   Fresh build. Needs offline.png.
# ---------------------------------------------------------------------------
def gen_browser_source_web_overlay() -> None:
    tid = "obs_browser_source_web_overlay"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    make_png(
        env_dir / "offline.png",
        size=(960, 540),
        color=(30, 30, 40),
        label="OFFLINE",
    )
    write_env(
        tid,
        [
            {"filename": "offline.png", "sandbox_path": "/home/user/Pictures/offline.png", "type": "png"}
        ],
    )


# ---------------------------------------------------------------------------
# Task 7: obs_rename_sources_not_scenes
#   One scene 'Show' with 4 generic-named sources.
# ---------------------------------------------------------------------------
def gen_rename_sources_not_scenes() -> None:
    tid = "obs_rename_sources_not_scenes"
    # Avoid parens in names. Use "Text FreeType 2" not "Text (FreeType 2)".
    names = [
        "Video Capture Device",
        "Audio Input Capture",
        "Display Capture",
        "Text FreeType 2",
    ]
    items = [make_scene_item(n) for n in names]
    col = build_collection({"Show": items})
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 8: obs_scene_split_refactor
#   One scene 'Everything' with 6 sources.
# ---------------------------------------------------------------------------
def gen_scene_split_refactor() -> None:
    tid = "obs_scene_split_refactor"
    names = ["Webcam", "Desktop", "Game Capture", "Intro Logo", "BRB Text", "End Card"]
    items = [make_scene_item(n) for n in names]
    col = build_collection({"Everything": items})
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


# ---------------------------------------------------------------------------
# Task 9: obs_event_multicam_six_scenes
#   Fresh build. Needs countdown.png.
# ---------------------------------------------------------------------------
def gen_event_multicam_six_scenes() -> None:
    tid = "obs_event_multicam_six_scenes"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    make_png(
        env_dir / "countdown.png",
        size=(800, 450),
        color=(10, 40, 80),
        label="Starting Soon",
    )
    write_env(
        tid,
        [
            {"filename": "countdown.png", "sandbox_path": "/home/user/Pictures/countdown.png", "type": "png"}
        ],
    )


# ---------------------------------------------------------------------------
# Task 10: obs_relocate_sources_across_scenes
#   2 scenes: Raw (all 5 sources), Target (empty).
# ---------------------------------------------------------------------------
def gen_relocate_sources_across_scenes() -> None:
    tid = "obs_relocate_sources_across_scenes"
    raw_items = [
        make_scene_item("Cam1"),
        make_scene_item("Cam2"),
        make_scene_item("Screen"),
        make_scene_item("Overlay"),
        make_scene_item("Bumper"),
    ]
    mapping = {
        "Raw": raw_items,
        "Target": [],
    }
    col = build_collection(mapping)
    save_collection(tid, col)
    write_env(
        tid,
        [
            {
                "filename": "scene_collection.json",
                "sandbox_path": "/home/user/.config/obs-studio/basic/scenes/Untitled.json",
                "type": "obs_scene_collection",
            }
        ],
    )


GENERATORS = {
    "obs_prune_crowded_scene": gen_prune_crowded_scene,
    "obs_hide_but_keep_sources": gen_hide_but_keep_sources,
    "obs_delete_unused_scenes": gen_delete_unused_scenes,
    "obs_news_broadcast_layout": gen_news_broadcast_layout,
    "obs_consolidate_into_single_scene": gen_consolidate_into_single_scene,
    "obs_browser_source_web_overlay": gen_browser_source_web_overlay,
    "obs_rename_sources_not_scenes": gen_rename_sources_not_scenes,
    "obs_scene_split_refactor": gen_scene_split_refactor,
    "obs_event_multicam_six_scenes": gen_event_multicam_six_scenes,
    "obs_relocate_sources_across_scenes": gen_relocate_sources_across_scenes,
}


def main() -> None:
    for tid, fn in GENERATORS.items():
        print(f"generating {tid}...")
        fn()
    # Verify all expected files exist.
    missing = []
    for tid in GENERATORS:
        mpath = TASKS_DIR / tid / "env_manifest.json"
        if not mpath.exists():
            missing.append(str(mpath))
            continue
        manifest = json.loads(mpath.read_text())
        for entry in manifest["files"]:
            fp = TASKS_DIR / tid / "env" / entry["filename"]
            if not fp.exists():
                missing.append(str(fp))
    if missing:
        print("MISSING:")
        for m in missing:
            print(" ", m)
        sys.exit(1)
    print("OK: all env files generated")


if __name__ == "__main__":
    main()
