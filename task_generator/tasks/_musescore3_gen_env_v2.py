"""
Generator for v2 musescore3 task env files. Extends the original builder in
_musescore3_gen_env.py with additional fixtures.

Run:
    python3 task_generator/tasks/_musescore3_gen_env_v2.py
"""

import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

BASE = Path(__file__).parent

# Load the original builder module dynamically since the filename starts with _
spec = importlib.util.spec_from_file_location(
    "ms_gen_env", BASE / "_musescore3_gen_env.py"
)
ms_gen_env = importlib.util.module_from_spec(spec)
sys.modules["ms_gen_env"] = ms_gen_env
spec.loader.exec_module(ms_gen_env)

build_mscx = ms_gen_env.build_mscx
write_mscz = ms_gen_env.write_mscz


SPECS = [
    {
        "task_id": "musescore3_multi_meta_publishing",
        "filename": "draft_song.mscz",
        "sandbox_path": "/home/user/Documents/draft_song.mscz",
        "kwargs": dict(
            title="Untitled",
            composer="Unknown",
            lyricist="",
            arranger="",
            copyright_="",
            measures=4,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_add_flute_instrument",
        "filename": "piano_only.mscz",
        "sandbox_path": "/home/user/Documents/piano_only.mscz",
        "kwargs": dict(
            title="Piano Study",
            composer="Test",
            measures=4,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
            parts=[("Piano", "Pno.", "keyboard.piano")],
        ),
    },
    {
        "task_id": "musescore3_set_eb_key_signature",
        "filename": "study_eb.mscz",
        "sandbox_path": "/home/user/Documents/study_eb.mscz",
        "kwargs": dict(
            title="Etude in C",
            composer="Test",
            measures=8,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_export_png_and_midi",
        "filename": "chorale.mscz",
        "sandbox_path": "/home/user/Documents/chorale.mscz",
        "kwargs": dict(
            title="Simple Chorale",
            composer="Test",
            measures=4,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_add_three_word_lyrics",
        "filename": "hymn.mscz",
        "sandbox_path": "/home/user/Documents/hymn.mscz",
        "kwargs": dict(
            title="Hymn",
            composer="Test",
            measures=3,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
            lyrics=False,
        ),
    },
    {
        "task_id": "musescore3_tempo_and_timesig_combo",
        "filename": "jig.mscz",
        "sandbox_path": "/home/user/Documents/jig.mscz",
        "kwargs": dict(
            title="Jig Sketch",
            composer="Test",
            measures=8,
            notes_per_measure=4,
            bps=1.5,  # 90 BPM initial
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_export_five_formats",
        "filename": "suite.mscz",
        "sandbox_path": "/home/user/Documents/suite.mscz",
        "kwargs": dict(
            title="Little Suite",
            composer="Test",
            measures=6,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_work_catalog_metadata",
        "filename": "catalog_entry.mscz",
        "sandbox_path": "/home/user/Documents/catalog_entry.mscz",
        "kwargs": dict(
            title="Untitled",
            composer="Composer",
            measures=4,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_rebuild_score_header",
        "filename": "waltz_draft.mscz",
        "sandbox_path": "/home/user/Documents/waltz_draft.mscz",
        "kwargs": dict(
            title="Waltz Draft",
            composer="",
            measures=4,
            notes_per_measure=4,
            bps=2.0,  # 120 BPM
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
    {
        "task_id": "musescore3_transcribe_and_export_midi_musicxml",
        "filename": "morning.mscz",
        "sandbox_path": "/home/user/Documents/morning.mscz",
        "kwargs": dict(
            title="Untitled",
            composer="",
            measures=4,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4,
            time_d=4,
        ),
    },
]


def main() -> None:
    for spec in SPECS:
        task_dir = BASE / spec["task_id"]
        env_dir = task_dir / "env"
        env_dir.mkdir(parents=True, exist_ok=True)
        out_path = env_dir / spec["filename"]
        mscx = build_mscx(**spec["kwargs"])
        write_mscz(out_path, mscx, inner_name=spec["filename"].replace(".mscz", ".mscx"))
        # Verify the .mscz parses and the inner .mscx is valid XML
        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            assert "META-INF/container.xml" in names, f"no container.xml in {out_path}"
            inner = [n for n in names if n.endswith(".mscx")]
            assert inner, f"no .mscx in {out_path}"
            data = zf.read(inner[0])
            ET.fromstring(data)
        manifest = {
            "task_id": spec["task_id"],
            "files": [
                {
                    "filename": spec["filename"],
                    "sandbox_path": spec["sandbox_path"],
                    "type": "mscz",
                }
            ],
        }
        with open(task_dir / "env_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")

    print(f"\nGenerated {len(SPECS)} musescore3 v2 fixtures.")


if __name__ == "__main__":
    main()
