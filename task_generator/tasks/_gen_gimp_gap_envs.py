"""Generate env assets for GIMP gap-fill tasks."""
import os
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))

def p(task_id, fname):
    d = os.path.join(BASE, task_id, "env")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, fname)

# 1. Multiply blend: yellow gradient base + cyan texture overlay (512x512)
img = Image.new("RGB", (512, 512))
for y in range(512):
    v = int(255 * y / 511)
    for x in range(512):
        img.putpixel((x, y), (255, 255, v))  # yellow -> white gradient vertically
img.save(p("gimp_gap_blend_mode_multiply_opacity", "photo_base.png"))
img2 = Image.new("RGB", (512, 512), (0, 200, 200))
# add a subtle diagonal stripe pattern
d2 = ImageDraw.Draw(img2)
for i in range(-512, 512, 32):
    d2.line([(i, 0), (i + 512, 512)], fill=(0, 150, 150), width=4)
img2.save(p("gimp_gap_blend_mode_multiply_opacity", "texture_overlay.png"))

# 2. Layer mask: provide two PNGs (red 400x300, blue 400x300). Agent adds mask + gradient in GIMP.
Image.new("RGB", (400, 300), (0, 0, 255)).save(p("gimp_gap_layer_mask_gradient_reveal", "blue_bg.png"))
Image.new("RGB", (400, 300), (255, 0, 0)).save(p("gimp_gap_layer_mask_gradient_reveal", "red_fg.png"))

# 3. Gaussian blur: sharp 8x8 checkerboard 400x400
img = Image.new("RGB", (400, 400), (255, 255, 255))
cell = 50
for cy in range(8):
    for cx in range(8):
        if (cx + cy) % 2 == 0:
            for y in range(cy * cell, (cy + 1) * cell):
                for x in range(cx * cell, (cx + 1) * cell):
                    img.putpixel((x, y), (0, 0, 0))
img.save(p("gimp_gap_gaussian_blur_filter", "checkerboard_sharp.png"))

# 4. Fuzzy select: white 400x400 with red 100x100 centered
img = Image.new("RGB", (400, 400), (255, 255, 255))
d_ = ImageDraw.Draw(img)
d_.rectangle([150, 150, 249, 249], fill=(255, 0, 0))
img.save(p("gimp_gap_fuzzy_select_fill", "red_square_on_white.png"))

# 5. Select by color: 3 vertical stripes 600x300
img = Image.new("RGB", (600, 300))
d_ = ImageDraw.Draw(img)
d_.rectangle([0, 0, 199, 299], fill=(255, 0, 0))
d_.rectangle([200, 0, 399, 299], fill=(0, 255, 0))
d_.rectangle([400, 0, 599, 299], fill=(0, 0, 255))
img.save(p("gimp_gap_select_by_color_replace", "three_stripes.png"))

# 6. Text layer: blank white 800x200
Image.new("RGB", (800, 200), (255, 255, 255)).save(p("gimp_gap_text_layer_heading", "blank_banner.png"))

# 7. Plasma: no input file

# 8. Gradient fill: no input file

# 9. Alpha cutout: white 300x300 with black star
from PIL import ImageDraw as ID
img = Image.new("RGB", (300, 300), (255, 255, 255))
d_ = ID.Draw(img)
# simple black star via polygon
import math
cx, cy, r1, r2 = 150, 150, 100, 40
pts = []
for i in range(10):
    a = -math.pi / 2 + i * math.pi / 5
    r = r1 if i % 2 == 0 else r2
    pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
d_.polygon(pts, fill=(0, 0, 0))
img.save(p("gimp_gap_alpha_channel_threshold_cutout", "silhouette.png"))

# 10. Screen blend: dark base + light top 500x500
Image.new("RGB", (500, 500), (40, 40, 80)).save(p("gimp_gap_two_layer_screen_blend", "dark_base.png"))
Image.new("RGB", (500, 500), (120, 120, 120)).save(p("gimp_gap_two_layer_screen_blend", "light_top.png"))

print("ALL ENV FILES GENERATED")

# Sanity verify each
from PIL import Image as I2
def verify(path, size=None, mode=None):
    im = I2.open(path)
    assert im.size == size if size else True, f"{path}: {im.size}"
    im.close()

for task in [
    "gimp_gap_blend_mode_multiply_opacity",
    "gimp_gap_layer_mask_gradient_reveal",
    "gimp_gap_gaussian_blur_filter",
    "gimp_gap_fuzzy_select_fill",
    "gimp_gap_select_by_color_replace",
    "gimp_gap_text_layer_heading",
    "gimp_gap_alpha_channel_threshold_cutout",
    "gimp_gap_two_layer_screen_blend",
]:
    d = os.path.join(BASE, task, "env")
    for f in os.listdir(d):
        if f.endswith(".png"):
            im = I2.open(os.path.join(d, f))
            print(f"  {task}/{f}: {im.size} {im.mode}")
            im.close()
