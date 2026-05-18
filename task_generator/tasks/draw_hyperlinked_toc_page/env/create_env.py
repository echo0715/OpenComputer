#!/usr/bin/env python3
"""Build report_toc.odg — a 4-page ODG with labeled rectangles per page."""
import os
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SCRIPT_DIR, "report_toc.odg")

LABELS = ["Intro Section", "Methods Section", "Results Section", "Appendix Section"]
PAGE_NAMES = ["page1", "page2", "page3", "page4"]


def _page(name: str, label: str) -> str:
    return (
        f'<draw:page draw:name="{name}" draw:master-page-name="Default">'
        f'<draw:rect draw:name="rect_{name}" svg:x="4cm" svg:y="4cm" svg:width="12cm" svg:height="4cm">'
        f'<text:p>{label}</text:p>'
        f'</draw:rect>'
        f'</draw:page>'
    )


pages_xml = "".join(_page(n, l) for n, l in zip(PAGE_NAMES, LABELS))

CONTENT = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
  xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  office:version="1.2">
  <office:body>
    <office:drawing>
      {pages_xml}
    </office:drawing>
  </office:body>
</office:document-content>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
  xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
  office:version="1.2">
 <office:automatic-styles>
  <style:page-layout style:name="PM0">
   <style:page-layout-properties fo:page-width="28cm" fo:page-height="21cm" fo:margin-top="1cm" fo:margin-bottom="1cm" fo:margin-left="1cm" fo:margin-right="1cm"/>
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
