"""Generate env files for 10 new CloudCompare tasks and verify them.

Run: python3 task_generator/tasks/_cloudcompare_v2_gen.py
"""
import json
import os
import random
import struct
import sys
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent
REPO = TASKS_DIR.parent.parent
sys.path.insert(0, str(REPO / "verifiers" / "cloudcompare"))
import cloudcompare as cc  # type: ignore

random.seed(20260411)


def write_ascii_ply_points(path: Path, pts):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("end_header\n")
        for x, y, z in pts:
            f.write(f"{x:.6f} {y:.6f} {z:.6f}\n")


def write_ascii_ply_points_rgb(path: Path, pts_rgb):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts_rgb)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for x, y, z, r, g, b in pts_rgb:
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {r} {g} {b}\n")


def write_ascii_xyz(path: Path, pts):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for p in pts:
            f.write(" ".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in p) + "\n")


def write_obj(path: Path, verts, faces):
    """faces: list of (a,b,c) 1-indexed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("# generated obj\n")
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for tri in faces:
            f.write("f " + " ".join(str(i) for i in tri) + "\n")


def rand_pts(n, lo, hi):
    return [(random.uniform(*lo), random.uniform(*lo), random.uniform(*lo))
            if False else (random.uniform(lo[0], hi[0]), random.uniform(lo[1], hi[1]), random.uniform(lo[2], hi[2]))
            for _ in range(n)]


def uniform_box(n, xlo, xhi, ylo, yhi, zlo, zhi):
    return [(random.uniform(xlo, xhi), random.uniform(ylo, yhi), random.uniform(zlo, zhi)) for _ in range(n)]


def make_env(task_id, files_info):
    env_dir = TASKS_DIR / task_id / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"task_id": task_id, "files": []}
    for fi in files_info:
        manifest["files"].append({
            "filename": fi["filename"],
            "sandbox_path": fi["sandbox_path"],
            "type": fi.get("type", Path(fi["filename"]).suffix.lstrip(".")),
        })
    with open(TASKS_DIR / task_id / "env_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# Task 1: obj_vertices_to_xyz — shape.obj (120 verts, 200+ faces)
# ---------------------------------------------------------------------------
def gen_task1():
    tid = "cloudcompare_obj_vertices_to_xyz"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    # Build a torus-like mesh: 10 major x 12 minor = 120 verts; 240 faces
    import math
    R, r = 5.0, 1.5
    major, minor = 10, 12
    verts = []
    for i in range(major):
        u = 2 * math.pi * i / major
        for j in range(minor):
            v = 2 * math.pi * j / minor
            x = (R + r * math.cos(v)) * math.cos(u)
            y = (R + r * math.cos(v)) * math.sin(u)
            z = r * math.sin(v)
            verts.append((x, y, z))
    faces = []
    for i in range(major):
        for j in range(minor):
            a = i * minor + j + 1
            b = ((i + 1) % major) * minor + j + 1
            c = ((i + 1) % major) * minor + ((j + 1) % minor) + 1
            d = i * minor + ((j + 1) % minor) + 1
            faces.append((a, b, c))
            faces.append((a, c, d))
    assert len(verts) == 120
    assert len(faces) >= 200
    write_obj(env_dir / "shape.obj", verts, faces)

    # verify
    info = cc._parse_obj(str(env_dir / "shape.obj"))
    assert info["vertex_count"] == 120, info
    assert info["face_count"] == len(faces), info
    make_env(tid, [{"filename": "shape.obj", "sandbox_path": "/home/user/Documents/shape.obj"}])
    print(f"  OK {tid}: verts={info['vertex_count']} faces={info['face_count']}")


# ---------------------------------------------------------------------------
# Task 2: translate_origin_bbox — offset.ply 400 pts in [95..105]^3
# ---------------------------------------------------------------------------
def gen_task2():
    tid = "cloudcompare_translate_origin_bbox"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    pts = uniform_box(400, 95.0, 105.0, 95.0, 105.0, 95.0, 105.0)
    write_ascii_ply_points(env_dir / "offset.ply", pts)
    info = cc._parse_ply(str(env_dir / "offset.ply"))
    assert info["vertex_count"] == 400
    assert 90 <= info["bbox"][0][0] <= 100
    make_env(tid, [{"filename": "offset.ply", "sandbox_path": "/home/user/Documents/offset.ply"}])
    print(f"  OK {tid}: {info['vertex_count']} pts bbox={info['bbox']}")


# ---------------------------------------------------------------------------
# Task 3: scale_cloud_2x — small.ply 250 pts x-extent ~22
# ---------------------------------------------------------------------------
def gen_task3():
    tid = "cloudcompare_scale_cloud_2x"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    # x-extent exactly 22 to avoid any ambiguity
    pts = uniform_box(248, 0.0, 22.0, 0.0, 22.0, 0.0, 22.0)
    pts.append((0.0, 0.0, 0.0))
    pts.append((22.0, 22.0, 22.0))
    write_ascii_ply_points(env_dir / "small.ply", pts)
    info = cc._parse_ply(str(env_dir / "small.ply"))
    assert info["vertex_count"] == 250
    x_extent = info["bbox"][1][0] - info["bbox"][0][0]
    assert 21.9 < x_extent < 22.1, x_extent
    make_env(tid, [{"filename": "small.ply", "sandbox_path": "/home/user/Documents/small.ply"}])
    print(f"  OK {tid}: 250 pts x_extent={x_extent}")


# ---------------------------------------------------------------------------
# Task 4: export_big_endian_ply — source.ply 450 pts ASCII
# ---------------------------------------------------------------------------
def gen_task4():
    tid = "cloudcompare_export_big_endian_ply"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    pts = uniform_box(450, -10.0, 10.0, -10.0, 10.0, -10.0, 10.0)
    write_ascii_ply_points(env_dir / "source.ply", pts)
    info = cc._parse_ply(str(env_dir / "source.ply"))
    assert info["vertex_count"] == 450 and info["format"] == "ascii"
    make_env(tid, [{"filename": "source.ply", "sandbox_path": "/home/user/Documents/source.ply"}])
    print(f"  OK {tid}: 450 ascii pts")


# ---------------------------------------------------------------------------
# Task 5: merge_three_clouds — north/south/east xyz (250/300/350)
# ---------------------------------------------------------------------------
def gen_task5():
    tid = "cloudcompare_merge_three_clouds"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    north = uniform_box(250, 0, 5, 0, 5, 0, 5)
    south = uniform_box(300, 0, 5, 10, 15, 0, 5)
    east = uniform_box(350, 10, 15, 0, 5, 0, 5)
    write_ascii_xyz(env_dir / "north.xyz", north)
    write_ascii_xyz(env_dir / "south.xyz", south)
    write_ascii_xyz(env_dir / "east.xyz", east)
    for name, n in (("north.xyz", 250), ("south.xyz", 300), ("east.xyz", 350)):
        info = cc._parse_ascii_cloud(str(env_dir / name))
        assert info["points"] == n, (name, info)
    make_env(tid, [
        {"filename": "north.xyz", "sandbox_path": "/home/user/Documents/north.xyz"},
        {"filename": "south.xyz", "sandbox_path": "/home/user/Documents/south.xyz"},
        {"filename": "east.xyz", "sandbox_path": "/home/user/Documents/east.xyz"},
    ])
    print(f"  OK {tid}: 250+300+350")


# ---------------------------------------------------------------------------
# Task 6: preserve_intensity_export — lidar_intensity.xyz (600 pts, 4 cols)
# ---------------------------------------------------------------------------
def gen_task6():
    tid = "cloudcompare_preserve_intensity_export"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    pts = []
    for _ in range(600):
        x = random.uniform(-20, 20)
        y = random.uniform(-20, 20)
        z = random.uniform(0, 5)
        intensity = random.uniform(0.0, 1.0)
        pts.append((x, y, z, intensity))
    write_ascii_xyz(env_dir / "lidar_intensity.xyz", pts)
    info = cc._parse_ascii_cloud(str(env_dir / "lidar_intensity.xyz"))
    assert info["points"] == 600 and info["columns"] == 4 and info["has_intensity"] is True, info
    make_env(tid, [{"filename": "lidar_intensity.xyz", "sandbox_path": "/home/user/Documents/lidar_intensity.xyz"}])
    print(f"  OK {tid}: 600 pts 4 cols has_intensity")


# ---------------------------------------------------------------------------
# Task 7: colorize_add_rgb — plain.ply 350 pts no color
# ---------------------------------------------------------------------------
def gen_task7():
    tid = "cloudcompare_colorize_add_rgb"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    pts = uniform_box(350, -5, 5, -5, 5, -5, 5)
    write_ascii_ply_points(env_dir / "plain.ply", pts)
    info = cc._parse_ply(str(env_dir / "plain.ply"))
    assert info["vertex_count"] == 350 and info["has_color"] is False, info
    make_env(tid, [{"filename": "plain.ply", "sandbox_path": "/home/user/Documents/plain.ply"}])
    print(f"  OK {tid}: 350 pts no color")


# ---------------------------------------------------------------------------
# Task 8: dense_crop_small_box — dense_field.ply 2000 pts in [0..20]^3
# ---------------------------------------------------------------------------
def gen_task8():
    tid = "cloudcompare_dense_crop_small_box"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    # Uniform in [0..20]^3 so roughly (10/20)^3 = 12.5% = 250 points fall in [5..15]^3
    pts = uniform_box(2000, 0, 20, 0, 20, 0, 20)
    write_ascii_ply_points(env_dir / "dense_field.ply", pts)
    info = cc._parse_ply(str(env_dir / "dense_field.ply"))
    assert info["vertex_count"] == 2000
    # count pts inside target box to sanity-check
    inside = sum(1 for (x, y, z) in pts if 5 <= x <= 15 and 5 <= y <= 15 and 5 <= z <= 15)
    assert inside >= 150, f"only {inside} pts inside target box"
    make_env(tid, [{"filename": "dense_field.ply", "sandbox_path": "/home/user/Documents/dense_field.ply"}])
    print(f"  OK {tid}: 2000 pts, {inside} inside [5..15]^3")


# ---------------------------------------------------------------------------
# Task 9: subsample_min_distance — thick.ply 1500 pts densely packed
# ---------------------------------------------------------------------------
def gen_task9():
    tid = "cloudcompare_subsample_min_distance"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    pts = uniform_box(1500, 0, 10, 0, 10, 0, 10)
    write_ascii_ply_points(env_dir / "thick.ply", pts)
    info = cc._parse_ply(str(env_dir / "thick.ply"))
    assert info["vertex_count"] == 1500
    make_env(tid, [{"filename": "thick.ply", "sandbox_path": "/home/user/Documents/thick.ply"}])
    print(f"  OK {tid}: 1500 pts")


# ---------------------------------------------------------------------------
# Task 10: obj_to_mesh_xyz_asc — gear.obj 48 verts 80 tris
# ---------------------------------------------------------------------------
def gen_task10():
    tid = "cloudcompare_obj_to_mesh_xyz_asc"
    env_dir = TASKS_DIR / tid / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    # Build two stacked 24-vertex rings (48 verts), 80 triangles: 48 side tris + 32 cap tris
    import math
    ring = 24
    verts = []
    for i in range(ring):
        a = 2 * math.pi * i / ring
        verts.append((math.cos(a) * 3.0, math.sin(a) * 3.0, 0.0))
    for i in range(ring):
        a = 2 * math.pi * i / ring
        verts.append((math.cos(a) * 3.0, math.sin(a) * 3.0, 2.0))
    faces = []
    # side: 2 tris per segment, 24 segments → 48 tris
    for i in range(ring):
        a = i + 1
        b = ((i + 1) % ring) + 1
        c = ring + ((i + 1) % ring) + 1
        d = ring + i + 1
        faces.append((a, b, c))
        faces.append((a, c, d))
    # bottom cap fan from vertex 1 → 22 tris
    for i in range(1, ring - 1):
        faces.append((1, i + 1, i + 2))
    # top cap fan from vertex ring+1 → 10 tris (to reach total 48+22+10=80)
    start = ring + 1
    for i in range(1, 11):
        faces.append((start, start + i + 1, start + i))
    assert len(verts) == 48
    assert len(faces) == 80, len(faces)
    write_obj(env_dir / "gear.obj", verts, faces)
    info = cc._parse_obj(str(env_dir / "gear.obj"))
    assert info["vertex_count"] == 48 and info["face_count"] == 80, info
    make_env(tid, [{"filename": "gear.obj", "sandbox_path": "/home/user/Documents/gear.obj"}])
    print(f"  OK {tid}: 48 v 80 f")


def main():
    gen_task1()
    gen_task2()
    gen_task3()
    gen_task4()
    gen_task5()
    gen_task6()
    gen_task7()
    gen_task8()
    gen_task9()
    gen_task10()
    print("ALL ENV GENERATION COMPLETE")


if __name__ == "__main__":
    main()
