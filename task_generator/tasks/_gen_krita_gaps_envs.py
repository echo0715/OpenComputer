"""Generate .kra env files for the krita coverage-gap tasks.

Reuses patterns from _gen_krita_envs.py but adds a keyframes sidecar for the
animated-layer fixture."""
import zipfile, struct, zlib, os, uuid, json
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


def create_kra(path, width=800, height=600, layers=None, title="Test",
               author="Tester", color_space="RGBA", x_res=300, y_res=300,
               img_name="test", framerate=24, animated_layer=None,
               keyframes=None):
    """Create a synthetic .kra. If `animated_layer` + `keyframes` are given,
    embed a keyframes sidecar XML for that layer."""
    if layers is None:
        layers = [{"name": "Background", "nodetype": "paintlayer",
                   "visible": "1", "opacity": "255"}]
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
        nodetype = layer.get("nodetype", "paintlayer")
        visible = layer.get("visible", "1")
        opacity = layer.get("opacity", "255")
        onionskin = layer.get("onionskin", "0")
        intimeline = layer.get("intimeline", "0")
        keyframes_attr = ""
        # If this layer has keyframes, mark it animated and point to sidecar
        if animated_layer and layer.get("name") == animated_layer:
            intimeline = "1"
            keyframes_attr = f' keyframes="{filename}.keyframes.xml"'

        attrs = (
            f'name="{layer.get("name","")}" nodetype="{nodetype}"'
            f' visible="{visible}" opacity="{opacity}"'
            f' filename="{filename}" uuid="{layer_uuid}"'
            f' compositeop="{compositeop}" colorspacename="{color_space}" collapsed="0"'
            f' intimeline="{intimeline}" x="0" y="0" colorlabel="0" onionskin="{onionskin}"'
            f' locked="{locked}" selected="{selected}" channelflags="" channellockflags=""'
            f'{keyframes_attr}'
        )
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
   <framerate value="{framerate}" type="value"/>
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
 </author>
</document-info>"""

    preview_scale = min(256 / max(width, height), 1.0)
    preview_w = max(1, int(width * preview_scale))
    preview_h = max(1, int(height * preview_scale))
    png_data = make_minimal_png(width, height, grayscale=is_gray)
    preview_data = make_minimal_png(preview_w, preview_h, grayscale=is_gray)

    anim_index_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE animation-metadata PUBLIC '-//KDE//DTD krita 1.1//EN' 'http://www.calligra.org/DTD/krita-1.1.dtd'>
<animation-metadata xmlns="http://www.calligra.org/DTD/krita">
 <framerate value="{framerate}" type="value"/>
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
        zf.writestr("mimetype", "application/x-krita",
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr("maindoc.xml", maindoc)
        zf.writestr("documentinfo.xml", documentinfo)
        zf.writestr("preview.png", preview_data)
        for filename, lname in layer_filenames:
            if lname == "Background":
                dpx = bytes([255, 255]) if is_gray else bytes([255, 255, 255, 255])
            else:
                dpx = bytes([0, 0]) if is_gray else bytes([0, 0, 0, 0])
            zf.writestr(f"{img_name}/layers/{filename}",
                        make_layer_data(pixel_size))
            zf.writestr(f"{img_name}/layers/{filename}.defaultpixel", dpx)
            # Embed keyframes sidecar for the animated layer
            if animated_layer and keyframes and lname == animated_layer:
                kf_parts = "\n".join(
                    f'   <keyframe time="{t}" color-label="0"/>'
                    for t in keyframes
                )
                kf_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE keyframes PUBLIC '-//KDE//DTD krita 1.1//EN' 'http://www.calligra.org/DTD/krita-1.1.dtd'>
<keyframes xmlns="http://www.calligra.org/DTD/krita">
{kf_parts}
</keyframes>
"""
                zf.writestr(
                    f"{img_name}/layers/{filename}.keyframes.xml", kf_xml)
        zf.writestr("mergedimage.png", png_data)
        zf.writestr(f"{img_name}/animation/index.xml", anim_index_xml)


# --- Task env specs ---
# (task_id, filename, kwargs-for-create_kra)
PL = lambda n, **kw: {
    "name": n, "nodetype": "paintlayer", "visible": "1", "opacity": "255", **kw
}

TASKS = [
    ("krita_add_transparency_mask", "portrait_mask.kra",
     dict(width=800, height=600, layers=[PL("Portrait")], title="Portrait Mask")),
    ("krita_add_filter_mask_blur", "scene.kra",
     dict(width=1024, height=768, layers=[PL("Background"), PL("Overlay")],
          title="Scene")),
    ("krita_add_vector_layer_rectangle", "frame.kra",
     dict(width=1024, height=768, layers=[PL("Canvas")], title="Frame")),
    ("krita_animation_three_keyframes", "bounce.kra",
     dict(width=640, height=480, layers=[PL("Ball")], title="Bounce",
          framerate=12)),
    ("krita_onion_skinning_enable", "walk_cycle.kra",
     dict(width=640, height=480, layers=[PL("Character")], title="Walk Cycle",
          framerate=24,
          animated_layer="Character", keyframes=[0, 6, 12])),
    ("krita_wrap_around_and_mirror", "pattern.kra",
     dict(width=512, height=512, layers=[PL("Paint")], title="Pattern")),
    ("krita_change_colorspace_grayscale", "photo_rgba.kra",
     dict(width=800, height=600, layers=[PL("Photo")], title="Photo")),
    ("krita_enable_python_plugin", "plugin_test.kra",
     dict(width=512, height=512, layers=[PL("Base")], title="Plugin Test")),
    ("krita_add_gradient_fill_layer", "sunset.kra",
     dict(width=1024, height=768, layers=[PL("Ground")], title="Sunset")),
    ("krita_transform_mask_rotation", "transform.kra",
     dict(width=800, height=600, layers=[PL("Subject")], title="Transform")),
    ("krita_selection_mask_on_layer", "mask_demo.kra",
     dict(width=800, height=600, layers=[PL("Foreground")],
          title="Mask Demo")),
]


def main():
    import xml.etree.ElementTree as ET
    for task_id, filename, kwargs in TASKS:
        out = BASE / task_id / "env" / filename
        create_kra(str(out), **kwargs)
        # verify
        with zipfile.ZipFile(str(out), "r") as zf:
            names = zf.namelist()
            assert "mimetype" in names, f"{out} missing mimetype"
            assert "maindoc.xml" in names, f"{out} missing maindoc.xml"
            assert "mergedimage.png" in names
            # Parse maindoc as sanity
            root = ET.fromstring(zf.read("maindoc.xml"))
            img = None
            for e in root.iter():
                t = e.tag.split("}")[-1]
                if t == "IMAGE":
                    img = e
                    break
            assert img is not None, f"{out} maindoc has no IMAGE"
            if kwargs.get("keyframes"):
                kf_found = [n for n in names if n.endswith(".keyframes.xml")]
                assert kf_found, f"{out} missing keyframes sidecar"
        print(f"OK {out}")

        # Write env_manifest.json
        manifest_path = BASE / task_id / "env_manifest.json"
        manifest = {
            "task_id": task_id,
            "files": [
                {
                    "filename": filename,
                    "sandbox_path": f"/home/user/Documents/{filename}",
                    "type": "kra",
                }
            ],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
