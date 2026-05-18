"""Write env_manifest.json for each darktable gap task and the combined file."""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))

TASK_IDS = [
    "darktable_gap_parametric_mask_luma",
    "darktable_gap_drawn_mask_circle_vignette",
    "darktable_gap_drawn_mask_gradient_sky",
    "darktable_gap_tone_equalizer",
    "darktable_gap_color_zones",
    "darktable_gap_color_calibration_wb",
    "darktable_gap_local_contrast",
    "darktable_gap_lens_correction",
    "darktable_gap_multi_instance_exposure",
    "darktable_gap_style_apply_selective",
    "darktable_gap_history_stack_compress",
]


def main():
    combined = []
    for tid in TASK_IDS:
        task_path = os.path.join(BASE, tid, "task.json")
        with open(task_path) as f:
            task = json.load(f)
        combined.append(task)
        # manifest
        files = []
        for f_ in task["env"]["files"]:
            files.append({
                "filename": f_["filename"],
                "sandbox_path": f_["sandbox_path"],
                "type": "jpg",
            })
        manifest = {"task_id": tid, "files": files}
        with open(os.path.join(BASE, tid, "env_manifest.json"), "w") as mf:
            json.dump(manifest, mf, indent=2)
        print(f"manifest: {tid} ({len(files)} files)")
    with open(os.path.join(BASE, "darktable_tasks.json"), "w") as cf:
        json.dump(combined, cf, indent=2)
    print(f"combined: darktable_tasks.json ({len(combined)} tasks)")


if __name__ == "__main__":
    main()
