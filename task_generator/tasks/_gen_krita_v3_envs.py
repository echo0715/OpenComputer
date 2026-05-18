"""Generate .kra env files for the 10 new krita tasks (v3 batch).

Reuses create_kra from _gen_krita_envs.py.
"""
import importlib.util, sys, json, zipfile
from pathlib import Path

BASE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("_krita_base", BASE / "_gen_krita_envs.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
create_kra = mod.create_kra
PL = mod.PL

# Group layer helper (nodetype=grouplayer).
def GL(name, children=None):
    # create_kra uses a flat list of layers — groups with children are not yet
    # supported. For this batch we fall back to seeding the four paint layers
    # flat; the agent re-groups them into the two target groups.
    return {"name": name, "nodetype": "grouplayer", "visible": "1", "opacity": "255", "compositeop": "normal"}


TASKS = [
    ("krita_add_adjustment_layer", "portrait.kra",
     dict(width=1024, height=1024, layers=[PL("Background")], title="Portrait", img_name="portrait")),
    ("krita_group_and_reorder_layers", "illustration.kra",
     dict(width=800, height=600,
          layers=[PL("Sky"), PL("Mountains"), PL("Trees"), PL("Character")],
          title="Illustration", img_name="illustration")),
    ("krita_resize_export_jpeg", "photo.kra",
     dict(width=1920, height=1080, layers=[PL("Background")], title="Photo", img_name="photo")),
    ("krita_flatten_and_export_png", "multilayer.kra",
     dict(width=1024, height=768,
          layers=[PL("L1"), PL("L2", opacity="200"), PL("L3", opacity="160"),
                  PL("L4", opacity="120"), PL("L5", opacity="80")],
          title="Multilayer", img_name="multilayer")),
    ("krita_create_new_canvas", "template.kra",
     dict(width=512, height=512, layers=[PL("Background")], title="Template", img_name="template")),
    ("krita_convert_grayscale", "color_artwork.kra",
     dict(width=800, height=600,
          layers=[PL("LayerA"), PL("LayerB"), PL("LayerC")],
          title="Color Artwork", img_name="artwork")),
    ("krita_export_multiple_formats", "logo.kra",
     dict(width=512, height=512, layers=[PL("Background")], title="Logo", img_name="logo")),
    ("krita_add_document_metadata", "artwork.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="Artwork", img_name="artwork")),
    ("krita_crop_and_add_border", "photo_crop.kra",
     dict(width=1600, height=900, layers=[PL("Background")], title="Photo Crop", img_name="photo")),
    ("krita_toggle_visibility_and_rename", "multi.kra",
     dict(width=800, height=600,
          layers=[PL("A"), PL("B"), PL("C")],
          title="Multi", img_name="multi")),
]


def main():
    for task_id, filename, kwargs in TASKS:
        out = BASE / task_id / "env" / filename
        create_kra(str(out), **kwargs)
        # Verify zip is openable and has the required internal files
        with zipfile.ZipFile(str(out), "r") as zf:
            names = set(zf.namelist())
            for req in ("mimetype", "maindoc.xml", "documentinfo.xml", "mergedimage.png"):
                assert req in names, f"{out} missing {req}"
            mimetype = zf.read("mimetype").decode()
            assert mimetype == "application/x-krita", f"{out} bad mimetype: {mimetype!r}"
        # Write env manifest
        manifest = {
            "task_id": task_id,
            "files": [
                {"filename": filename,
                 "sandbox_path": f"/home/user/Documents/{filename}",
                 "type": "kra"}
            ],
        }
        (BASE / task_id / "env_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"OK {out}  size={out.stat().st_size}")


if __name__ == "__main__":
    main()
