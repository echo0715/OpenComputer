#!/usr/bin/env python3
"""Create an ODG file with 4 rectangles (Box A, Box B, Box C, Box D) for the edit shapes task."""
import zipfile
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(SCRIPT_DIR, "draft_diagram.odg")

MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
                   manifest:version="1.2">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.graphics" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="styles.xml"/>
</manifest:manifest>
"""

CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
    xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
    office:version="1.2">
  <office:body>
    <office:drawing>
      <draw:page draw:name="page1" draw:master-page-name="Default">
        <draw:rect draw:name="BoxA" svg:x="10cm" svg:y="2cm" svg:width="6cm" svg:height="3cm">
          <text:p>Box A</text:p>
        </draw:rect>
        <draw:rect draw:name="BoxB" svg:x="10cm" svg:y="7cm" svg:width="6cm" svg:height="3cm">
          <text:p>Box B</text:p>
        </draw:rect>
        <draw:rect draw:name="BoxC" svg:x="10cm" svg:y="12cm" svg:width="6cm" svg:height="3cm">
          <text:p>Box C</text:p>
        </draw:rect>
        <draw:rect draw:name="BoxD" svg:x="10cm" svg:y="17cm" svg:width="6cm" svg:height="3cm">
          <text:p>Box D</text:p>
        </draw:rect>
      </draw:page>
    </office:drawing>
  </office:body>
</office:document-content>
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

with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
    zf.writestr("META-INF/manifest.xml", MANIFEST_XML)
    zf.writestr("content.xml", CONTENT_XML)
    zf.writestr("styles.xml", STYLES_XML)

print(f"Created {OUTPUT}")
