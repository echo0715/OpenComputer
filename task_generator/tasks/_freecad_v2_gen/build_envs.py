"""Build env FCStd files for freecad v2 tasks and verify they parse."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_fcstd import build_fcstd, verify_fcstd  # noqa

TASKS_DIR = os.path.abspath(os.path.join(HERE, ".."))


def env_path(task_id, filename):
    d = os.path.join(TASKS_DIR, task_id, "env")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)


def write_manifest(task_id, files):
    manifest = {"task_id": task_id, "files": files}
    p = os.path.join(TASKS_DIR, task_id, "env_manifest.json")
    with open(p, "w") as f:
        json.dump(manifest, f, indent=2)


TASKS = []


def task(task_id, filename, sandbox_path, doc_label, objects, expected_types):
    out = env_path(task_id, filename)
    build_fcstd(out, doc_label, objects)
    expected_names = [o["name"] for o in objects]
    verify_fcstd(out, expected_names, expected_types)
    write_manifest(task_id, [{
        "filename": filename,
        "sandbox_path": sandbox_path,
        "type": "fcstd",
    }])
    print(f"OK  {task_id}  -> {out}")


# 1. chain.FCStd — Box, Cylinder, Sphere (starting primitives for boolean chain)
task(
    "freecad_multi_boolean_chain",
    "chain.FCStd",
    "/home/user/Documents/chain.FCStd",
    doc_label="chain",
    objects=[
        {"name": "Box", "type": "Part::Box",
         "kwargs": {"label": "Box", "length": 20, "width": 20, "height": 20}},
        {"name": "Cylinder", "type": "Part::Cylinder",
         "kwargs": {"label": "Cylinder", "radius": 5, "height": 40}},
        {"name": "Sphere", "type": "Part::Sphere",
         "kwargs": {"label": "Sphere", "radius": 12}},
    ],
    expected_types={
        "Box": "Part::Box",
        "Cylinder": "Part::Cylinder",
        "Sphere": "Part::Sphere",
    },
)

# 2. cone.FCStd — default Cone (R1=2, R2=0, H=10)
task(
    "freecad_cone_frustum_redesign",
    "cone.FCStd",
    "/home/user/Documents/cone.FCStd",
    doc_label="cone",
    objects=[
        {"name": "Cone", "type": "Part::Cone",
         "kwargs": {"label": "Cone", "radius1": 2, "radius2": 0, "height": 10}},
    ],
    expected_types={"Cone": "Part::Cone"},
)

# 3. widget.FCStd — Box 40x30x25 ready for multi-format export
task(
    "freecad_export_multi_format",
    "widget.FCStd",
    "/home/user/Documents/widget.FCStd",
    doc_label="widget",
    objects=[
        {"name": "Box", "type": "Part::Box",
         "kwargs": {"label": "Box", "length": 40, "width": 30, "height": 25}},
    ],
    expected_types={"Box": "Part::Box"},
)

# 4. parts_catalog.FCStd — 4 primitives
task(
    "freecad_rename_four_objects",
    "parts_catalog.FCStd",
    "/home/user/Documents/parts_catalog.FCStd",
    doc_label="parts_catalog",
    objects=[
        {"name": "Box", "type": "Part::Box",
         "kwargs": {"label": "Box", "length": 15, "width": 15, "height": 5}},
        {"name": "Cylinder", "type": "Part::Cylinder",
         "kwargs": {"label": "Cylinder", "radius": 4, "height": 20}},
        {"name": "Sphere", "type": "Part::Sphere",
         "kwargs": {"label": "Sphere", "radius": 6}},
        {"name": "Cone", "type": "Part::Cone",
         "kwargs": {"label": "Cone", "radius1": 5, "radius2": 1, "height": 12}},
    ],
    expected_types={
        "Box": "Part::Box",
        "Cylinder": "Part::Cylinder",
        "Sphere": "Part::Sphere",
        "Cone": "Part::Cone",
    },
)

# 5. ring.FCStd — empty document
task(
    "freecad_torus_parametric",
    "ring.FCStd",
    "/home/user/Documents/ring.FCStd",
    doc_label="ring",
    objects=[],
    expected_types={},
)

# 6. report.FCStd — empty document (agent sets doc metadata)
task(
    "freecad_document_metadata_bundle",
    "report.FCStd",
    "/home/user/Documents/report.FCStd",
    doc_label="report",
    objects=[],
    expected_types={},
)

# 7. empty_prefs.FCStd — empty doc so FreeCAD can launch
task(
    "freecad_preferences_multi_tune",
    "empty_prefs.FCStd",
    "/home/user/Documents/empty_prefs.FCStd",
    doc_label="empty_prefs",
    objects=[],
    expected_types={},
)

# 8. twin.FCStd — two Part::Box
task(
    "freecad_fuse_two_boxes",
    "twin.FCStd",
    "/home/user/Documents/twin.FCStd",
    doc_label="twin",
    objects=[
        {"name": "Box", "type": "Part::Box",
         "kwargs": {"label": "Box", "length": 20, "width": 20, "height": 10}},
        {"name": "Box001", "type": "Part::Box",
         "kwargs": {"label": "Box001", "length": 10, "width": 10, "height": 30}},
    ],
    expected_types={"Box": "Part::Box", "Box001": "Part::Box"},
)

# 9. ball.FCStd — Part::Sphere r=30
task(
    "freecad_sphere_stl_export_high_res",
    "ball.FCStd",
    "/home/user/Documents/ball.FCStd",
    doc_label="ball",
    objects=[
        {"name": "Sphere", "type": "Part::Sphere",
         "kwargs": {"label": "Sphere", "radius": 30}},
    ],
    expected_types={"Sphere": "Part::Sphere"},
)

# 10. assembly.FCStd — Box, Cylinder, Cone
task(
    "freecad_compound_of_primitives",
    "assembly.FCStd",
    "/home/user/Documents/assembly.FCStd",
    doc_label="assembly",
    objects=[
        {"name": "Box", "type": "Part::Box",
         "kwargs": {"label": "Box", "length": 12, "width": 12, "height": 12}},
        {"name": "Cylinder", "type": "Part::Cylinder",
         "kwargs": {"label": "Cylinder", "radius": 5, "height": 15}},
        {"name": "Cone", "type": "Part::Cone",
         "kwargs": {"label": "Cone", "radius1": 6, "radius2": 0, "height": 10}},
    ],
    expected_types={
        "Box": "Part::Box",
        "Cylinder": "Part::Cylinder",
        "Cone": "Part::Cone",
    },
)

print("\nAll env files generated and verified.")
