"""Create an empty Blender scene for the nested-collections task."""
import os
import subprocess
import sys

BLEND_PATH = "/home/user/Documents/nested_cols.blend"

script = f"""
import bpy
import os
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
os.makedirs(os.path.dirname({BLEND_PATH!r}), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath={BLEND_PATH!r})
print("BLEND_CREATED")
"""

with open("/tmp/_gen_blend.py", "w") as f:
    f.write(script)

r = subprocess.run(
    ["blender", "-b", "--python", "/tmp/_gen_blend.py"],
    capture_output=True, text=True, timeout=60,
)
if "BLEND_CREATED" not in r.stdout:
    print(f"Error creating blend: {r.stderr[:500]}", file=sys.stderr)
    sys.exit(1)
print(f"Created {BLEND_PATH}")
