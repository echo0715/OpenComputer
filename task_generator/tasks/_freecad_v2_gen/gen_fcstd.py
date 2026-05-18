"""Minimal FreeCAD .FCStd (Document.xml-only) generator for v2 tasks.

FreeCAD's verifier reads Document.xml out of the .FCStd zip. We do not
need BRP shape blobs or thumbnails for verification — only the XML
object/property structure. This script writes valid FCStd files that the
verifier can parse, FreeCAD GUI can open (BREP shapes are recomputed on
load for native primitives), and agents can manipulate in-place.
"""

from __future__ import annotations

import os
import textwrap
import uuid
import zipfile
from pathlib import Path


DOC_TEMPLATE = '''<?xml version='1.0' encoding='utf-8'?>
<!--
 FreeCAD Document, see https://www.freecadweb.org for more information...
-->
<Document SchemaVersion="4" ProgramVersion="0.19R" FileVersion="1">
    <Properties Count="15" TransientCount="3">
        <_Property name="FileName" type="App::PropertyString" status="50331649"/>
        <_Property name="Tip" type="App::PropertyLink" status="33554433"/>
        <_Property name="TransientDir" type="App::PropertyString" status="50331649"/>
        <Property name="Comment" type="App::PropertyString">
            <String value=""/>
        </Property>
        <Property name="Company" type="App::PropertyString">
            <String value=""/>
        </Property>
        <Property name="CreatedBy" type="App::PropertyString">
            <String value=""/>
        </Property>
        <Property name="CreationDate" type="App::PropertyString" status="16777217">
            <String value="2026-04-11T00:00:00Z"/>
        </Property>
        <Property name="Id" type="App::PropertyString">
            <String value=""/>
        </Property>
        <Property name="Label" type="App::PropertyString" status="1">
            <String value="{doc_label}"/>
        </Property>
        <Property name="LastModifiedBy" type="App::PropertyString">
            <String value=""/>
        </Property>
        <Property name="LastModifiedDate" type="App::PropertyString" status="16777217">
            <String value="2026-04-11T00:00:00Z"/>
        </Property>
        <Property name="License" type="App::PropertyString" status="1">
            <String value="All rights reserved"/>
        </Property>
        <Property name="LicenseURL" type="App::PropertyString" status="1">
            <String value="http://en.wikipedia.org/wiki/All_rights_reserved"/>
        </Property>
        <Property name="Material" type="App::PropertyMap">
            <Map count="0">
            </Map>
        </Property>
        <Property name="Meta" type="App::PropertyMap">
            <Map count="0">
            </Map>
        </Property>
        <Property name="ShowHidden" type="App::PropertyBool" status="1">
            <Bool value="false"/>
        </Property>
        <Property name="TipName" type="App::PropertyString" status="83886080">
            <String value=""/>
        </Property>
        <Property name="Uid" type="App::PropertyUUID" status="16777217">
            <Uuid value="{uid}"/>
        </Property>
    </Properties>
    <Objects Count="{obj_count}" Dependencies="1">
{objects_decl}
    </Objects>
    <ObjectData Count="{obj_count}">
{object_data}
    </ObjectData>
</Document>
'''


# --- Property fragments (indented to sit inside <Properties>) ----------------

def _prop_float(name, ptype, value):
    return (f'                <Property name="{name}" type="{ptype}">\n'
            f'                    <Float value="{float(value):.16f}"/>\n'
            f'                </Property>')


def _prop_int(name, ptype, value):
    return (f'                <Property name="{name}" type="{ptype}">\n'
            f'                    <Integer value="{int(value)}"/>\n'
            f'                </Property>')


def _prop_string(name, value, status="134217728"):
    # Escape & and <>
    v = (value.replace("&", "&amp;")
         .replace("<", "&lt;").replace(">", "&gt;"))
    return (f'                <Property name="{name}" type="App::PropertyString" '
            f'status="{status}">\n'
            f'                    <String value="{v}"/>\n'
            f'                </Property>')


def _prop_bool(name, ptype, value):
    v = "true" if value else "false"
    return (f'                <Property name="{name}" type="{ptype}">\n'
            f'                    <Bool value="{v}"/>\n'
            f'                </Property>')


def _prop_placement():
    return ('                <Property name="Placement" type="App::PropertyPlacement" status="8388608">\n'
            '                    <PropertyPlacement Px="0.0000000000000000" Py="0.0000000000000000" Pz="0.0000000000000000" Q0="0.0000000000000000" Q1="0.0000000000000000" Q2="0.0000000000000000" Q3="1.0000000000000000" A="0.0000000000000000" Ox="0.0000000000000000" Oy="0.0000000000000000" Oz="1.0000000000000000"/>\n'
            '                </Property>')


def _prop_visibility():
    return ('                <Property name="Visibility" type="App::PropertyBool" status="648">\n'
            '                    <Bool value="true"/>\n'
            '                </Property>')


# --- Object builders ---------------------------------------------------------
# We always include Label + Label2 + Placement + Visibility + the shape-specific
# parameters. We do NOT reference a Part::PropertyPartShape (no .brp blobs),
# because the verifier parses Document.xml only. FreeCAD itself recomputes the
# shape on file open for primitives.

_HEADER = ('            <Properties Count="{count}" TransientCount="0">')
_FOOTER = '            </Properties>\n        </Object>'


def _wrap_object(name, extensions, props):
    parts = []
    parts.append(f'        <Object name="{name}" Extensions="True">')
    parts.append('            <Extensions Count="1">')
    parts.append(f'                <Extension type="Part::AttachExtension" name="AttachExtension">')
    parts.append('                </Extension>')
    parts.append('            </Extensions>')
    parts.append(_HEADER.format(count=len(props)))
    parts.extend(props)
    parts.append(_FOOTER)
    return "\n".join(parts)


def make_box(name, label, length, width, height, label2=""):
    props = [
        _prop_float("Height", "App::PropertyLength", height),
        _prop_string("Label", label, status="134217728"),
        _prop_string("Label2", label2, status="67108992"),
        _prop_float("Length", "App::PropertyLength", length),
        _prop_placement(),
        _prop_visibility(),
        _prop_float("Width", "App::PropertyLength", width),
    ]
    return _wrap_object(name, True, props)


def make_cylinder(name, label, radius, height, angle=360.0, label2=""):
    props = [
        _prop_float("Angle", "App::PropertyAngle", angle),
        _prop_float("Height", "App::PropertyLength", height),
        _prop_string("Label", label, status="134217728"),
        _prop_string("Label2", label2, status="67108992"),
        _prop_placement(),
        _prop_float("Radius", "App::PropertyLength", radius),
        _prop_visibility(),
    ]
    return _wrap_object(name, True, props)


def make_sphere(name, label, radius, angle1=-90.0, angle2=90.0, angle3=360.0, label2=""):
    props = [
        _prop_float("Angle1", "App::PropertyAngle", angle1),
        _prop_float("Angle2", "App::PropertyAngle", angle2),
        _prop_float("Angle3", "App::PropertyAngle", angle3),
        _prop_string("Label", label, status="134217728"),
        _prop_string("Label2", label2, status="67108992"),
        _prop_placement(),
        _prop_float("Radius", "App::PropertyLength", radius),
        _prop_visibility(),
    ]
    return _wrap_object(name, True, props)


def make_cone(name, label, radius1, radius2, height, angle=360.0, label2=""):
    props = [
        _prop_float("Angle", "App::PropertyAngle", angle),
        _prop_float("Height", "App::PropertyLength", height),
        _prop_string("Label", label, status="134217728"),
        _prop_string("Label2", label2, status="67108992"),
        _prop_placement(),
        _prop_float("Radius1", "App::PropertyLength", radius1),
        _prop_float("Radius2", "App::PropertyLength", radius2),
        _prop_visibility(),
    ]
    return _wrap_object(name, True, props)


OBJ_KINDS = {
    "Part::Box": make_box,
    "Part::Cylinder": make_cylinder,
    "Part::Sphere": make_sphere,
    "Part::Cone": make_cone,
}


def build_fcstd(out_path: str, doc_label: str, objects: list[dict]):
    """objects = [{name, type, builder_kwargs}]"""
    decls = []
    datas = []
    for i, obj in enumerate(objects):
        name = obj["name"]
        otype = obj["type"]
        builder = OBJ_KINDS[otype]
        decls.append(f'        <ObjectDeps Name="{name}" Count="0"/>')
        decls.append(f'        <Object type="{otype}" name="{name}" id="{100 + i}" />')
        datas.append(builder(name, **obj["kwargs"]))

    doc_xml = DOC_TEMPLATE.format(
        doc_label=doc_label,
        uid=str(uuid.uuid4()),
        obj_count=len(objects),
        objects_decl="\n".join(decls) if decls else "",
        object_data="\n".join(datas) if datas else "",
    )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Document.xml", doc_xml)

    return out_path


def verify_fcstd(path: str, expected_object_names: list[str], expected_types: dict):
    """Parse the FCStd with the project verifier and assert key properties."""
    import sys
    sys.path.insert(0, "/Users/Mike/Desktop/syn_env/verifiers/freecad")
    from freecad import FreeCADVerifier  # type: ignore

    v = FreeCADVerifier()
    info = v.get_document_info(path)
    assert "error" not in info, info
    objs = v.get_objects(path)
    assert "error" not in objs, objs
    names = [o["name"] for o in objs["objects"]]
    for n in expected_object_names:
        assert n in names, f"missing object {n} in {path}; got {names}"
    for n, t in expected_types.items():
        r = v.check_object_type(path, n, t)
        assert r["match"], f"type mismatch for {n}: {r}"
    return True
