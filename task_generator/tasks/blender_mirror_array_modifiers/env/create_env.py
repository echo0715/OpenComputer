"""Create default Blender scene at the expected save path."""
import os
import subprocess
import sys

BLEND_PATH = "/home/user/Documents/mirror_array.blend"

script = """
import bpy
import os
os.makedirs(os.path.dirname("/home/user/Documents/mirror_array.blend"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath="/home/user/Documents/mirror_array.blend")
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
