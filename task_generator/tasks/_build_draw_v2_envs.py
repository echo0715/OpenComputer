#!/usr/bin/env python3
"""Generate ODG seed files for libreoffice_draw v2 tasks.

Builds minimal ODG (OpenDocument Graphics) files containing a small number
of rectangles/ellipses that each task is designed around. Then verifies
each file opens and contains the expected text.
"""
import os
import zipfile

TASKS_DIR = os.path.dirname(os.path.abspath(__file__))

MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
                   manifest:version="1.2">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.graphics" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="styles.xml"/>
</manifest:manifest>
"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    office:version="1.2">
  <office:automatic-styles>
    <style:page-layout style:name="PM0">
      <style:page-layout-properties fo:page-width="28cm" fo:page-height="21cm" fo:margin-top="1cm" fo:margin-bottom="1cm" fo:margin-left="1cm" fo:margin-right="1cm"/>
    </style:page-layout>
  </office:automatic-styles>
  <office:master-styles>
    <style:master-page style:name="Default" style:page-layout-name="PM0" draw:style-name="dp1"/>
  </office:master-styles>
</office:document-styles>
"""

MIMETYPE = "application/vnd.oasis.opendocument.graphics"

CONTENT_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
    xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
    office:version="1.2">
  <office:body>
    <office:drawing>
"""
CONTENT_FOOTER = """    </office:drawing>
  </office:body>
</office:document-content>
"""


def rect(name, x, y, w, h, text):
    return (
        f'        <draw:rect draw:name="{name}" svg:x="{x}cm" svg:y="{y}cm" '
        f'svg:width="{w}cm" svg:height="{h}cm">\n'
        f'          <text:p>{text}</text:p>\n'
        f'        </draw:rect>\n'
    )


def ellipse(name, x, y, w, h, text):
    return (
        f'        <draw:ellipse draw:name="{name}" svg:x="{x}cm" svg:y="{y}cm" '
        f'svg:width="{w}cm" svg:height="{h}cm">\n'
        f'          <text:p>{text}</text:p>\n'
        f'        </draw:ellipse>\n'
    )


def page_xml(page_name, shapes_xml):
    return (
        f'      <draw:page draw:name="{page_name}" draw:master-page-name="Default">\n'
        f"{shapes_xml}"
        f'      </draw:page>\n'
    )


def write_odg(out_path, pages_xml):
    content_xml = CONTENT_HEADER + pages_xml + CONTENT_FOOTER
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", MANIFEST_XML)
        zf.writestr("content.xml", content_xml)
        zf.writestr("styles.xml", STYLES_XML)


# ---------------------------------------------------------------------------
# Per-task fixture definitions.
# Each entry: (task_id, filename, pages_xml_builder, expected_texts)
# ---------------------------------------------------------------------------

def build_class_stub():
    shapes = rect("Animal", 11, 3, 6, 3, "Animal")
    return page_xml("page1", shapes)


def build_topology_base():
    shapes = ellipse("Internet", 11, 2, 6, 3, "Internet")
    return page_xml("page1", shapes)


def build_mindmap_seed():
    shapes = ellipse("ML", 11, 8, 7, 4, "Machine Learning")
    return page_xml("page1", shapes)


def build_state_seed():
    shapes = ellipse("Red", 3, 3, 4, 4, "Red")
    return page_xml("page1", shapes)


def build_family_root():
    shapes = rect("Grandpa", 8, 2, 5, 2, "Grandpa John")
    shapes += rect("Grandma", 15, 2, 5, 2, "Grandma Mary")
    return page_xml("page1", shapes)


FIXTURES = [
    (
        "draw_uml_class_diagram",
        "class_stub.odg",
        build_class_stub,
        ["Animal"],
    ),
    (
        "draw_network_topology",
        "topology_base.odg",
        build_topology_base,
        ["Internet"],
    ),
    (
        "draw_mind_map_topics",
        "mindmap_seed.odg",
        build_mindmap_seed,
        ["Machine Learning"],
    ),
    (
        "draw_state_machine_traffic",
        "state_seed.odg",
        build_state_seed,
        ["Red"],
    ),
    (
        "draw_family_tree_layers",
        "family_root.odg",
        build_family_root,
        ["Grandpa John", "Grandma Mary"],
    ),
]


def verify(odg_path, expected_texts):
    """Re-open the ODG and confirm each expected text is present."""
    with zipfile.ZipFile(odg_path, "r") as zf:
        names = zf.namelist()
        assert "mimetype" in names, f"{odg_path}: missing mimetype"
        assert "content.xml" in names, f"{odg_path}: missing content.xml"
        assert "META-INF/manifest.xml" in names, f"{odg_path}: missing manifest"
        content = zf.read("content.xml").decode("utf-8")
        for txt in expected_texts:
            assert txt in content, f"{odg_path}: missing expected text {txt!r}"
    # Confirm mimetype is stored (first entry, uncompressed).
    with open(odg_path, "rb") as f:
        head = f.read(38)
    assert b"mimetype" in head, f"{odg_path}: mimetype not first"


def main():
    for task_id, filename, builder, expected in FIXTURES:
        env_dir = os.path.join(TASKS_DIR, task_id, "env")
        os.makedirs(env_dir, exist_ok=True)
        out_path = os.path.join(env_dir, filename)
        pages = builder()
        write_odg(out_path, pages)
        verify(out_path, expected)
        size = os.path.getsize(out_path)
        print(f"OK  {task_id}/{filename}  ({size} bytes)")


if __name__ == "__main__":
    main()
