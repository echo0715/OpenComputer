"""Generate .kra env files for krita tasks by reusing create_test_kra logic."""
import zipfile, struct, zlib, os, uuid, io
from pathlib import Path

BASE = Path(__file__).parent


def make_minimal_png(width, height, color=(255, 255, 255, 255), grayscale=False):
    def chunk(t, data):
        c = t + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc
    header = b"\x89PNG\r\n\x1a\n"
    if grayscale:
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 4, 0, 0, 0))
        pixel = bytes([color[0], color[3] if len(color) >= 4 else 255])
    else:
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        pixel = bytes(color[:4])
    row = b"\x00" + pixel * width
    idat = chunk(b"IDAT", zlib.compress(row * height))
    iend = chunk(b"IEND", b"")
    return header + ihdr + idat + iend


def make_layer_data(pixel_size=4):
    return f"VERSION 2\nTILEWIDTH 64\nTILEHEIGHT 64\nPIXELSIZE {pixel_size}\nDATA 0\n".encode()


def create_kra(path, width=800, height=600, layers=None, title="Test", author="Tester",
               color_space="RGBA", x_res=300, y_res=300, img_name="test"):
    if layers is None:
        layers = [{"name": "Background", "nodetype": "paintlayer", "visible": "1", "opacity": "255"}]
    is_gray = color_space == "GRAYA"
    pixel_size = 2 if is_gray else 4

    layer_xml_parts = []
    layer_filenames = []
    for i, layer in enumerate(layers):
        filename = f"layer{i + 2}"
        layer_uuid = "{" + str(uuid.uuid4()) + "}"
        layer_filenames.append((filename, layer.get("name", f"Layer {i}")))
        locked = "1" if layer.get("name") == "Background" else "0"
        selected = "true" if i == 0 else "false"
        compositeop = layer.get("compositeop", "normal")
        attrs = " ".join(f'{k}="{v}"' for k, v in layer.items() if k != "compositeop")
        attrs += f' filename="{filename}" uuid="{layer_uuid}"'
        attrs += f' compositeop="{compositeop}" colorspacename="{color_space}" collapsed="0"'
        attrs += f' intimeline="1" x="0" y="0" colorlabel="0" onionskin="0"'
        attrs += f' locked="{locked}" selected="{selected}" channelflags="" channellockflags=""'
        layer_xml_parts.append(f"   <layer {attrs}/>")
    layers_xml = "\n".join(layer_xml_parts)

    maindoc = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE DOC PUBLIC '-//KDE//DTD krita 2.0//EN' 'http://www.calligra.org/DTD/krita-2.0.dtd'>
<DOC xmlns="http://www.calligra.org/DTD/krita" kritaVersion="5.0.2" editor="Krita" syntaxVersion="2.0">
 <IMAGE x-res="{x_res}" y-res="{y_res}" width="{width}" name="{img_name}" colorspacename="{color_space}" mime="application/x-kra" height="{height}" description="" profile="sRGB-elle-V2-srgbtrc.icc">
  <layers>
{layers_xml}
  </layers>
  <ProjectionBackgroundColor ColorData="AAAAAA=="/>
  <GlobalAssistantsColor SimpleColorData="176,176,176,255"/>
  <Palettes/>
  <resources/>
  <animation>
   <framerate value="24" type="value"/>
   <range to="100" from="0" type="timerange"/>
   <currentTime value="0" type="value"/>
  </animation>
 </IMAGE>
</DOC>"""

    documentinfo = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE document-info PUBLIC '-//KDE//DTD document-info 1.1//EN' 'http://www.calligra.org/DTD/document-info-1.1.dtd'>
<document-info xmlns="http://www.calligra.org/DTD/document-info">
 <about>
  <title>{title}</title>
  <description></description>
  <subject>krita task</subject>
  <abstract><![CDATA[Seed file for a krita GUI task]]></abstract>
  <keyword></keyword>
  <initial-creator>Unknown</initial-creator>
  <editing-cycles>1</editing-cycles>
  <editing-time></editing-time>
  <date>2026-04-12T00:00:00</date>
  <creation-date>2026-04-12T00:00:00</creation-date>
  <language></language>
  <license></license>
 </about>
 <author>
  <full-name>{author}</full-name>
  <creator-first-name></creator-first-name>
  <creator-last-name></creator-last-name>
  <initial></initial>
  <author-title></author-title>
  <position></position>
  <company></company>
 </author>
</document-info>"""

    preview_scale = min(256 / max(width, height), 1.0)
    preview_w = max(1, int(width * preview_scale))
    preview_h = max(1, int(height * preview_scale))
    png_data = make_minimal_png(width, height, grayscale=is_gray)
    preview_data = make_minimal_png(preview_w, preview_h, grayscale=is_gray)

    anim_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE animation-metadata PUBLIC '-//KDE//DTD krita 1.1//EN' 'http://www.calligra.org/DTD/krita-1.1.dtd'>
<animation-metadata xmlns="http://www.calligra.org/DTD/krita">
 <framerate value="24" type="value"/>
 <range to="100" from="0" type="timerange"/>
 <currentTime value="0" type="value"/>
 <export-settings>
  <sequenceFilePath value="" type="value"/>
  <sequenceBaseName value="" type="value"/>
  <sequenceInitialFrameNumber value="-1" type="value"/>
 </export-settings>
</animation-metadata>
"""

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/x-krita", compress_type=zipfile.ZIP_STORED)
        zf.writestr("maindoc.xml", maindoc)
        zf.writestr("documentinfo.xml", documentinfo)
        zf.writestr("preview.png", preview_data)
        for filename, lname in layer_filenames:
            if lname == "Background":
                dpx = bytes([255, 255]) if is_gray else bytes([255, 255, 255, 255])
            else:
                dpx = bytes([0, 0]) if is_gray else bytes([0, 0, 0, 0])
            zf.writestr(f"{img_name}/layers/{filename}", make_layer_data(pixel_size))
            zf.writestr(f"{img_name}/layers/{filename}.defaultpixel", dpx)
        zf.writestr("mergedimage.png", png_data)
        zf.writestr(f"{img_name}/animation/index.xml", anim_xml)


PL = lambda n, op="normal", vis="1", opacity="255": {
    "name": n, "nodetype": "paintlayer", "visible": vis, "opacity": opacity, "compositeop": op
}

TASKS = [
    ("krita_add_paint_layer_named", "painting.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="Painting")),
    ("krita_resize_canvas_1024", "canvas.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="Canvas")),
    ("krita_export_png", "artwork.kra",
     dict(width=640, height=480, layers=[PL("Background")], title="Artwork")),
    ("krita_rename_and_reorder_layers", "scene.kra",
     dict(width=800, height=600, layers=[PL("Layer 1"), PL("Layer 2"), PL("Layer 3")], title="Scene")),
    ("krita_set_layer_opacity", "opacity.kra",
     dict(width=800, height=600, layers=[PL("Background"), PL("Overlay")], title="Opacity")),
    ("krita_toggle_layer_visibility", "sketches.kra",
     dict(width=800, height=600, layers=[PL("Sketch"), PL("Color"), PL("Lineart")], title="Sketches")),
    ("krita_change_layer_blend_mode", "blend.kra",
     dict(width=800, height=600, layers=[PL("Base"), PL("Shadows")], title="Blend")),
    ("krita_group_layers", "face.kra",
     dict(width=800, height=600, layers=[PL("Eyes"), PL("Nose"), PL("Mouth")], title="Face")),
    ("krita_flatten_image", "multi.kra",
     dict(width=800, height=600, layers=[PL("Background"), PL("Mid"), PL("Top")], title="Multi")),
    ("krita_export_jpeg_quality", "photo.kra",
     dict(width=640, height=480, layers=[PL("Background")], title="Photo")),
]


def main():
    for task_id, filename, kwargs in TASKS:
        out = BASE / task_id / "env" / filename
        create_kra(str(out), **kwargs)
        # verify
        with zipfile.ZipFile(str(out), "r") as zf:
            assert "maindoc.xml" in zf.namelist(), f"{out} missing maindoc.xml"
            assert "mergedimage.png" in zf.namelist()
        print(f"OK {out}")


if __name__ == "__main__":
    main()
