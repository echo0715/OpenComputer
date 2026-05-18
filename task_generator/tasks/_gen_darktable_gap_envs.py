"""Generate env images for darktable gap-coverage tasks."""
import os
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))


def save(img: Image.Image, task_id: str, filename: str) -> str:
    d = os.path.join(BASE, task_id, "env")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, filename)
    # JPEG for all except GPX
    img.save(path, quality=92)
    return path


def grad_horizon(w=800, h=600, sky=(135, 190, 230), ground=(80, 110, 60)):
    img = Image.new("RGB", (w, h), sky)
    d = ImageDraw.Draw(img)
    d.rectangle([0, h // 2, w, h], fill=ground)
    # add a few mountains
    d.polygon([(100, h // 2), (220, h // 2 - 120), (340, h // 2)], fill=(70, 85, 60))
    d.polygon([(300, h // 2), (450, h // 2 - 160), (600, h // 2)], fill=(60, 75, 55))
    return img


def contrast_zones(w=800, h=600):
    img = Image.new("RGB", (w, h), (128, 128, 128))
    d = ImageDraw.Draw(img)
    # shadows band
    d.rectangle([0, 0, w, h // 3], fill=(30, 30, 30))
    # midtones band
    d.rectangle([0, h // 3, w, 2 * h // 3], fill=(128, 128, 128))
    # highlights band
    d.rectangle([0, 2 * h // 3, w, h], fill=(230, 230, 230))
    return img


def portrait_circle(w=600, h=800):
    img = Image.new("RGB", (w, h), (40, 40, 60))
    d = ImageDraw.Draw(img)
    # subject face
    cx, cy, r = w // 2, h // 2, 150
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(220, 180, 150))
    d.ellipse([cx - 60, cy - 40, cx - 30, cy - 10], fill=(30, 30, 30))
    d.ellipse([cx + 30, cy - 40, cx + 60, cy - 10], fill=(30, 30, 30))
    d.arc([cx - 50, cy + 10, cx + 50, cy + 70], start=0, end=180, fill=(60, 20, 20), width=4)
    return img


def color_blocks(w=800, h=600):
    img = Image.new("RGB", (w, h), (200, 200, 200))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w // 3, h], fill=(200, 40, 40))
    d.rectangle([w // 3, 0, 2 * w // 3, h], fill=(40, 180, 60))
    d.rectangle([2 * w // 3, 0, w, h], fill=(40, 80, 200))
    return img


def patches_neutral(w=800, h=600):
    img = Image.new("RGB", (w, h), (180, 180, 180))
    d = ImageDraw.Draw(img)
    patches = [
        (30, 30, 30), (80, 80, 80), (130, 130, 130),
        (180, 180, 180), (220, 220, 220),
        (220, 80, 80), (80, 180, 80), (80, 80, 220),
        (220, 200, 80), (200, 80, 200), (80, 200, 200),
    ]
    cols = 4
    pw, ph = w // cols, h // 3
    for i, c in enumerate(patches):
        r, col = divmod(i, cols)
        d.rectangle([col * pw + 10, r * ph + 10, (col + 1) * pw - 10, (r + 1) * ph - 10], fill=c)
    return img


def textured_landscape(w=1000, h=750):
    img = Image.new("RGB", (w, h), (150, 170, 140))
    d = ImageDraw.Draw(img)
    # sky
    d.rectangle([0, 0, w, h // 2], fill=(170, 200, 225))
    # ground with stripes for texture
    for i in range(h // 2, h, 10):
        shade = 80 + (i % 40)
        d.rectangle([0, i, w, i + 5], fill=(shade, shade + 20, shade - 10))
    # trees
    for x in range(50, w, 120):
        d.polygon([(x, h // 2), (x - 30, h // 2 + 60), (x + 30, h // 2 + 60)], fill=(40, 80, 40))
    return img


def grid_image(w=1000, h=750):
    img = Image.new("RGB", (w, h), (245, 245, 235))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 50):
        d.line([(x, 0), (x, h)], fill=(30, 30, 30), width=1)
    for y in range(0, h, 50):
        d.line([(0, y), (w, y)], fill=(30, 30, 30), width=1)
    # a subject
    d.rectangle([w // 2 - 120, h // 2 - 80, w // 2 + 120, h // 2 + 80], fill=(180, 60, 60))
    return img


def generic_scene(seed=0, w=800, h=600):
    import random
    rng = random.Random(seed)
    img = Image.new("RGB", (w, h), (rng.randint(80, 200), rng.randint(80, 200), rng.randint(80, 200)))
    d = ImageDraw.Draw(img)
    for _ in range(12):
        x0, y0 = rng.randint(0, w - 50), rng.randint(0, h - 50)
        x1, y1 = x0 + rng.randint(30, 200), y0 + rng.randint(30, 200)
        c = (rng.randint(20, 240), rng.randint(20, 240), rng.randint(20, 240))
        d.rectangle([x0, y0, x1, y1], fill=c)
    return img


# Task -> (image builder, filename)
TASKS = {
    "darktable_gap_parametric_mask_luma": [(grad_horizon(), "landscape_luma.jpg")],
    "darktable_gap_drawn_mask_circle_vignette": [(portrait_circle(), "portrait_circle.jpg")],
    "darktable_gap_drawn_mask_gradient_sky": [(grad_horizon(), "sky_gradient.jpg")],
    "darktable_gap_tone_equalizer": [(contrast_zones(), "tone_eq_source.jpg")],
    "darktable_gap_color_zones": [(color_blocks(), "color_zones_source.jpg")],
    "darktable_gap_color_calibration_wb": [(patches_neutral(), "wb_source.jpg")],
    "darktable_gap_local_contrast": [(textured_landscape(), "local_contrast_source.jpg")],
    "darktable_gap_lens_correction": [(grid_image(), "lens_source.jpg")],
    "darktable_gap_multi_instance_exposure": [(generic_scene(1), "multi_inst_source.jpg")],
    "darktable_gap_style_apply_selective": [
        (generic_scene(2), "img_a.jpg"),
        (generic_scene(3), "img_b.jpg"),
        (generic_scene(4), "img_c.jpg"),
    ],
    "darktable_gap_history_stack_compress": [(generic_scene(5), "history_source.jpg")],
}


def main():
    for task_id, items in TASKS.items():
        for img, fn in items:
            p = save(img, task_id, fn)
            # verify
            with Image.open(p) as im:
                im.load()
                assert im.size[0] > 0
            print(f"wrote {p} ({im.size})")


if __name__ == "__main__":
    main()
