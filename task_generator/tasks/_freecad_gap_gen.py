"""Generator for FreeCAD 'gap' task env files.

Produces minimal-but-valid FCStd files containing the required starting state
for each gap task. Each FCStd is a ZIP with Document.xml (no GuiDocument, no
BREP needed for the starting state — FreeCAD will compute them on open).

The verifier reads objects via ObjectData/Object elements with their
Properties children. We write both <Objects><Object type=... name=.../>
and <ObjectData><Object name=...><Properties>...</Properties></Object>.
"""
import os
import zipfile
from pathlib import Path
from datetime import datetime


TASKS_DIR = Path(__file__).parent

DOC_HEADER = """<?xml version='1.0' encoding='utf-8'?>
<!--
 FreeCAD Document, generated synthetically for gap tasks
-->
<Document SchemaVersion="4" ProgramVersion="0.19R" FileVersion="1">
    <Properties Count="4" TransientCount="0">
        <Property name="Comment" type="App::PropertyString"><String value=""/></Property>
        <Property name="Label" type="App::PropertyString" status="1"><String value="{label}"/></Property>
        <Property name="CreationDate" type="App::PropertyString" status="16777217"><String value="{date}"/></Property>
        <Property name="Uid" type="App::PropertyUUID" status="16777217"><Uuid value="00000000-0000-0000-0000-000000000000"/></Property>
    </Properties>
"""
DOC_FOOTER = """</Document>
"""


def _objects_xml(objs):
    """Build <Objects> + <ObjectData> sections.
    objs: list of dicts {name, type, properties: [(pname, ptype, inner_xml), ...]}
    """
    lines = []
    lines.append(f'    <Objects Count="{len(objs)}" Dependencies="0">')
    for o in objs:
        lines.append(f'        <ObjectDeps Name="{o["name"]}" Count="0"/>')
    for o in objs:
        lines.append(f'        <Object type="{o["type"]}" name="{o["name"]}" id="1" />')
    lines.append('    </Objects>')
    lines.append(f'    <ObjectData Count="{len(objs)}">')
    for o in objs:
        lines.append(f'        <Object name="{o["name"]}">')
        props = o.get("properties", [])
        lines.append(f'            <Properties Count="{len(props)}" TransientCount="0">')
        for pname, ptype, inner in props:
            lines.append(f'                <Property name="{pname}" type="{ptype}">{inner}</Property>')
        lines.append('            </Properties>')
        lines.append('        </Object>')
    lines.append('    </ObjectData>')
    return "\n".join(lines) + "\n"


def _label_prop(label):
    return ("Label", "App::PropertyString", f'<String value="{label}"/>')


def _float_prop(name, value, proptype="App::PropertyLength"):
    return (name, proptype, f'<Float value="{float(value)}"/>')


def _int_prop(name, value, proptype="App::PropertyInteger"):
    return (name, proptype, f'<Integer value="{int(value)}"/>')


def _bool_prop(name, value):
    return (name, "App::PropertyBool", f'<Bool value="{"true" if value else "false"}"/>')


def build_fcstd(path: Path, label: str, objs: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = DOC_HEADER.format(label=label, date=date) + _objects_xml(objs) + DOC_FOOTER
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Document.xml", xml)
    return path


# ---------------------------------------------------------------------------
# Task env definitions
# ---------------------------------------------------------------------------

TASKS = {
    "freecad_gap_sketch_constrained_rectangle": {
        "file": "sketch_start.FCStd",
        "label": "SketchDoc",
        "objs": [],
    },
    "freecad_gap_partdesign_pad_bracket": {
        "file": "bracket_start.FCStd",
        "label": "BracketDoc",
        "objs": [],
    },
    "freecad_gap_partdesign_pocket_plate": {
        "file": "plate_start.FCStd",
        "label": "PlateDoc",
        "objs": [
            {
                "name": "PlateBody",
                "type": "PartDesign::Body",
                "properties": [_label_prop("PlateBody")],
            },
            {
                "name": "BasePlate",
                "type": "PartDesign::Pad",
                "properties": [
                    _label_prop("BasePlate"),
                    _float_prop("Length", 10.0),
                    _bool_prop("Midplane", False),
                ],
            },
        ],
    },
    "freecad_gap_partdesign_revolve_bottle": {
        "file": "bottle_start.FCStd",
        "label": "BottleDoc",
        "objs": [],
    },
    "freecad_gap_partdesign_fillet_chamfer": {
        "file": "cube_start.FCStd",
        "label": "CubeDoc",
        "objs": [
            {
                "name": "CubeBody",
                "type": "PartDesign::Body",
                "properties": [_label_prop("CubeBody")],
            },
            {
                "name": "Cube",
                "type": "PartDesign::Pad",
                "properties": [
                    _label_prop("Cube"),
                    _float_prop("Length", 40.0),
                ],
            },
        ],
    },
    "freecad_gap_partdesign_linear_pattern_holes": {
        "file": "strip_start.FCStd",
        "label": "StripDoc",
        "objs": [
            {
                "name": "StripBody",
                "type": "PartDesign::Body",
                "properties": [_label_prop("StripBody")],
            },
            {
                "name": "Strip",
                "type": "PartDesign::Pad",
                "properties": [
                    _label_prop("Strip"),
                    _float_prop("Length", 10.0),
                ],
            },
            {
                "name": "PilotHole",
                "type": "PartDesign::Pocket",
                "properties": [
                    _label_prop("PilotHole"),
                    _float_prop("Length", 10.0),
                ],
            },
        ],
    },
    "freecad_gap_partdesign_circular_pattern_lugs": {
        "file": "disk_start.FCStd",
        "label": "DiskDoc",
        "objs": [
            {
                "name": "DiskBody",
                "type": "PartDesign::Body",
                "properties": [_label_prop("DiskBody")],
            },
            {
                "name": "Disk",
                "type": "PartDesign::Pad",
                "properties": [
                    _label_prop("Disk"),
                    _float_prop("Length", 10.0),
                ],
            },
        ],
    },
    "freecad_gap_draft_wire_polygon": {
        "file": "draft_start.FCStd",
        "label": "DraftDoc",
        "objs": [],
    },
    "freecad_gap_techdraw_views_dims": {
        "file": "techdraw_start.FCStd",
        "label": "TechDrawDoc",
        "objs": [
            {
                "name": "Block",
                "type": "Part::Box",
                "properties": [
                    _label_prop("Block"),
                    _float_prop("Length", 60.0),
                    _float_prop("Width", 40.0),
                    _float_prop("Height", 20.0),
                ],
            },
        ],
    },
    "freecad_gap_spreadsheet_parametric": {
        "file": "spreadsheet_start.FCStd",
        "label": "SpreadsheetDoc",
        "objs": [],
    },
    "freecad_gap_fem_analysis_cantilever": {
        "file": "fem_start.FCStd",
        "label": "FemDoc",
        "objs": [
            {
                "name": "Beam",
                "type": "Part::Box",
                "properties": [
                    _label_prop("Beam"),
                    _float_prop("Length", 200.0),
                    _float_prop("Width", 20.0),
                    _float_prop("Height", 10.0),
                ],
            },
        ],
    },
    "freecad_gap_path_cam_job": {
        "file": "path_start.FCStd",
        "label": "PathDoc",
        "objs": [
            {
                "name": "Stock",
                "type": "Part::Box",
                "properties": [
                    _label_prop("Stock"),
                    _float_prop("Length", 80.0),
                    _float_prop("Width", 60.0),
                    _float_prop("Height", 10.0),
                ],
            },
        ],
    },
    "freecad_gap_assembly4_two_parts": {
        "file": "asm_start.FCStd",
        "label": "AsmDoc",
        "objs": [
            {
                "name": "Base",
                "type": "App::Part",
                "properties": [_label_prop("Base")],
            },
            {
                "name": "Lid",
                "type": "App::Part",
                "properties": [_label_prop("Lid")],
            },
        ],
    },
}


def main():
    import json
    for tid, spec in TASKS.items():
        tdir = TASKS_DIR / tid
        env_dir = tdir / "env"
        env_dir.mkdir(parents=True, exist_ok=True)
        fpath = env_dir / spec["file"]
        build_fcstd(fpath, spec["label"], spec["objs"])
        print(f"[ok] wrote {fpath}")
        # Verify
        with zipfile.ZipFile(fpath, "r") as z:
            assert "Document.xml" in z.namelist(), f"missing Document.xml in {fpath}"
            data = z.read("Document.xml").decode()
            assert "<Document " in data
            for o in spec["objs"]:
                assert o["name"] in data, f"object {o['name']} missing in {fpath}"
        # Manifest
        manifest = {
            "task_id": tid,
            "files": [
                {
                    "filename": spec["file"],
                    "sandbox_path": f"/home/user/Documents/{spec['file']}",
                    "type": "fcstd",
                }
            ],
        }
        (tdir / "env_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("done")


if __name__ == "__main__":
    main()
