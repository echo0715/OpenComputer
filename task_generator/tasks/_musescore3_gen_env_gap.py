"""Generate env files for musescore3 gap-coverage tasks."""

import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

BASE = Path(__file__).parent

spec = importlib.util.spec_from_file_location("ms_gen_env", BASE / "_musescore3_gen_env.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["ms_gen_env"] = mod
spec.loader.exec_module(mod)

build_mscx = mod.build_mscx
write_mscz = mod.write_mscz


SPECS = [
    {
        "task_id": "musescore3_gap_staccato_articulation",
        "filename": "staccato_etude.mscz",
        "kwargs": dict(title="Staccato Etude", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_accent_tenuto_mix",
        "filename": "expression_study.mscz",
        "kwargs": dict(title="Expression Study", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_trill_ornament",
        "filename": "baroque_sketch.mscz",
        "kwargs": dict(title="Baroque Sketch", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_dynamics_mf_ff",
        "filename": "dynamic_arc.mscz",
        "kwargs": dict(title="Dynamic Arc", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_crescendo_hairpin",
        "filename": "swell.mscz",
        "kwargs": dict(title="Swell", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_chord_symbols",
        "filename": "leadsheet.mscz",
        "kwargs": dict(title="Lead Sheet", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_voltas_repeats",
        "filename": "folk_tune.mscz",
        "kwargs": dict(title="Folk Tune", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_dc_al_fine",
        "filename": "sonatina_dc.mscz",
        "kwargs": dict(title="Sonatina DC", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_page_layout_margins",
        "filename": "score_layout.mscz",
        "kwargs": dict(title="Score Layout", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_system_breaks",
        "filename": "break_study.mscz",
        "kwargs": dict(title="Break Study", composer="Test", measures=12, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_midscore_instrument_change",
        "filename": "woodwind_switch.mscz",
        "kwargs": dict(title="Woodwind Switch", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4,
                       parts=[("Clarinet", "Cl.", "wind.reed.clarinet.bflat")]),
    },
    {
        "task_id": "musescore3_gap_pedal_marks",
        "filename": "pedal_study.mscz",
        "kwargs": dict(title="Pedal Study", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
    {
        "task_id": "musescore3_gap_fingering_numbers",
        "filename": "finger_study.mscz",
        "kwargs": dict(title="Finger Study", composer="Test", measures=4, notes_per_measure=4, bps=2.0, key_acc=0, time_n=4, time_d=4),
    },
]


def main():
    for spec in SPECS:
        task_dir = BASE / spec["task_id"]
        env_dir = task_dir / "env"
        env_dir.mkdir(parents=True, exist_ok=True)
        out_path = env_dir / spec["filename"]
        mscx = build_mscx(**spec["kwargs"])
        inner = spec["filename"].replace(".mscz", ".mscx")
        write_mscz(out_path, mscx, inner_name=inner)
        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            assert "META-INF/container.xml" in names
            mscx_list = [n for n in names if n.endswith(".mscx")]
            assert mscx_list
            ET.fromstring(zf.read(mscx_list[0]))
        manifest = {
            "task_id": spec["task_id"],
            "files": [{
                "filename": spec["filename"],
                "sandbox_path": f"/home/user/Documents/{spec['filename']}",
                "type": "mscz",
            }],
        }
        with open(task_dir / "env_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
