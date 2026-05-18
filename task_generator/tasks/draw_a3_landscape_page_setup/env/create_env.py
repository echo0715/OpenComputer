#!/usr/bin/env python3
"""Create report_draft.odg — single A4 portrait page with a 'Draft Content' rectangle."""
import os
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SCRIPT_DIR, "report_draft.odg")

CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
  xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  office:version="1.2">
  <office:body>
    <office:drawing>
      <draw:page draw:name="page1" draw:master-page-name="Default">
        <draw:rect draw:name="draftContent" svg:x="4cm" svg:y="4cm" svg:width="12cm" svg:height="4cm">
          <text:p>Draft Content</text:p>
        </draw:rect>
      </draw:page>
    </office:drawing>
  </office:body>
</office:document-content>
"""

# Note: A4 portrait, margins 1cm (to be changed by agent to A3 landscape, margins 2cm).
STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
  xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
  office:version="1.2">
 <office:automatic-styles>
  <style:page-layout style:name="PM0">
   <style:page-layout-properties fo:page-width="21cm" fo:page-height="29.7cm"
      fo:margin-top="1cm" fo:margin-bottom="1cm"
      fo:margin-left="1cm" fo:margin-right="1cm"/>
  </style:page-layout>
 </office:automatic-styles>
 <office:master-styles>
  <style:master-page style:name="Default" style:page-layout-name="PM0"/>
 </office:master-styles>
</office:document-styles>
"""

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.graphics" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="styles.xml"/>
</manifest:manifest>
"""

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("mimetype", "application/vnd.oasis.opendocument.graphics",
               compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/manifest.xml", MANIFEST)
    z.writestr("content.xml", CONTENT)
    z.writestr("styles.xml", STYLES)

print(f"Created {OUT}")
