#!/usr/bin/env python3
"""Generate env SVGs and task.json files for Inkscape gap tasks."""
import json, os, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/Users/Mike/Desktop/syn_env/task_generator/tasks")

SVG_NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"'

def write_task(task_id, env_files, svg_generators, task_json):
    tdir = ROOT / task_id
    edir = tdir / "env"
    edir.mkdir(parents=True, exist_ok=True)
    for fname, content in svg_generators.items():
        (edir / fname).write_text(content)
    # Write manifest
    manifest = {"task_id": task_id, "files": [{"filename": f["filename"], "sandbox_path": f["sandbox_path"], "type": f["filename"].split(".")[-1]} for f in env_files]}
    (tdir / "env_manifest.json").write_text(json.dumps(manifest, indent=2))
    (tdir / "task.json").write_text(json.dumps(task_json, indent=2))
    # Verify XML parses
    for fname, content in svg_generators.items():
        if fname.endswith(".svg"):
            ET.fromstring(content)

tasks = []

# -------------------- Task 1: boolean union + difference --------------------
svg1 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="600" height="400" viewBox="0 0 600 400">
  <circle id="circA" cx="150" cy="120" r="70" fill="#cc3333"/>
  <circle id="circB" cx="210" cy="120" r="70" fill="#3333cc"/>
  <rect id="sqA" x="340" y="60" width="140" height="140" fill="#33aa33"/>
  <rect id="sqB" x="420" y="140" width="140" height="140" fill="#ee8833"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_boolean_union_difference",
    "app": "inkscape",
    "task": "Open /home/user/Documents/booleans.svg in Inkscape. Perform two path boolean operations:\n1. UNION of the two circles (circA red and circB blue). Replace both with a single path whose id is 'circUnion' and fill is '#884488'.\n2. DIFFERENCE of sqA (green) minus sqB (orange). Replace both squares with a single path whose id is 'sqDiff' and fill is '#228866'.\n\nSave the file in place at /home/user/Documents/booleans.svg. The original circA/circB/sqA/sqB elements should no longer exist.",
    "env": {"files": [{"filename": "booleans.svg", "sandbox_path": "/home/user/Documents/booleans.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/booleans.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/booleans.svg circUnion", "key": "exists", "expected": True, "description": "circUnion path exists"},
        {"command": "check-element-exists /home/user/Documents/booleans.svg sqDiff", "key": "exists", "expected": True, "description": "sqDiff path exists"},
        {"command": "check-element-exists /home/user/Documents/booleans.svg circA", "key": "exists", "expected": False, "description": "Original circA removed"},
        {"command": "check-element-exists /home/user/Documents/booleans.svg circB", "key": "exists", "expected": False, "description": "Original circB removed"},
        {"command": "check-element-exists /home/user/Documents/booleans.svg sqA", "key": "exists", "expected": False, "description": "Original sqA removed"},
        {"command": "check-element-exists /home/user/Documents/booleans.svg sqB", "key": "exists", "expected": False, "description": "Original sqB removed"},
        {"command": "check-style-property /home/user/Documents/booleans.svg circUnion fill #884488", "key": "match", "expected": True, "description": "circUnion fill"},
        {"command": "check-style-property /home/user/Documents/booleans.svg sqDiff fill #228866", "key": "match", "expected": True, "description": "sqDiff fill"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"booleans.svg": svg1}, tasks[-1])

# -------------------- Task 2: trio intersect/exclusion/division --------------------
svg2 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="700" height="600" viewBox="0 0 700 600">
  <!-- Row 1: Intersection -->
  <circle id="r1a" cx="200" cy="100" r="70" fill="#aa2288"/>
  <circle id="r1b" cx="280" cy="100" r="70" fill="#22aaee"/>
  <!-- Row 2: Exclusion -->
  <rect id="r2a" x="130" y="240" width="140" height="140" fill="#ddcc22"/>
  <circle id="r2b" cx="300" cy="310" r="70" fill="#cc4444"/>
  <!-- Row 3: Division -->
  <rect id="r3a" x="120" y="440" width="240" height="120" fill="#337744"/>
  <rect id="r3b" x="220" y="470" width="60" height="160" fill="#ffffff"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_boolean_trio_intersection_exclusion_division",
    "app": "inkscape",
    "task": "Open /home/user/Documents/trio_bool.svg. Perform three boolean operations, one per row:\n- Row 1 (r1a and r1b circles): INTERSECTION. Result path id 'rowIntersect', fill '#ff8800'.\n- Row 2 (r2a rect and r2b circle): EXCLUSION (symmetric difference). Result id 'rowExclusion', fill '#0088ff'.\n- Row 3 (r3a large rect, r3b small rect overlapping it): DIVISION (cut r3a with r3b). Tag the LARGER resulting piece with id 'rowDivide' and fill '#22aa44'.\nSave /home/user/Documents/trio_bool.svg in place.",
    "env": {"files": [{"filename": "trio_bool.svg", "sandbox_path": "/home/user/Documents/trio_bool.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/trio_bool.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/trio_bool.svg rowIntersect", "key": "exists", "expected": True, "description": "Intersection result"},
        {"command": "check-element-exists /home/user/Documents/trio_bool.svg rowExclusion", "key": "exists", "expected": True, "description": "Exclusion result"},
        {"command": "check-element-exists /home/user/Documents/trio_bool.svg rowDivide", "key": "exists", "expected": True, "description": "Division result"},
        {"command": "check-style-property /home/user/Documents/trio_bool.svg rowIntersect fill #ff8800", "key": "match", "expected": True, "description": "Intersect fill"},
        {"command": "check-style-property /home/user/Documents/trio_bool.svg rowExclusion fill #0088ff", "key": "match", "expected": True, "description": "Exclusion fill"},
        {"command": "check-style-property /home/user/Documents/trio_bool.svg rowDivide fill #22aa44", "key": "match", "expected": True, "description": "Division fill"}
    ],
    "metadata": {"complexity": 5, "data_generatability": 5, "estimated_difficulty": 5}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"trio_bool.svg": svg2}, tasks[-1])

# -------------------- Task 3: clip + mask --------------------
svg3 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="800" height="400" viewBox="0 0 800 400">
  <g id="grid">
    <rect x="20" y="20" width="60" height="60" fill="#ff3333"/>
    <rect x="90" y="20" width="60" height="60" fill="#33ff33"/>
    <rect x="160" y="20" width="60" height="60" fill="#3333ff"/>
    <rect x="230" y="20" width="60" height="60" fill="#ffcc33"/>
    <rect x="20" y="90" width="60" height="60" fill="#33ccff"/>
    <rect x="90" y="90" width="60" height="60" fill="#ff33cc"/>
    <rect x="160" y="90" width="60" height="60" fill="#99cc00"/>
    <rect x="230" y="90" width="60" height="60" fill="#cc3300"/>
  </g>
  <circle id="clipShape" cx="150" cy="100" r="90" fill="#000000"/>
  <g id="grid2" transform="translate(440,0)">
    <rect x="20" y="20" width="60" height="60" fill="#ff3333"/>
    <rect x="90" y="20" width="60" height="60" fill="#33ff33"/>
    <rect x="160" y="20" width="60" height="60" fill="#3333ff"/>
    <rect x="20" y="90" width="60" height="60" fill="#ffcc33"/>
    <rect x="90" y="90" width="60" height="60" fill="#33ccff"/>
    <rect x="160" y="90" width="60" height="60" fill="#ff33cc"/>
  </g>
  <rect id="maskShape" x="460" y="20" width="240" height="160" fill="#ffffff"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_clip_and_mask",
    "app": "inkscape",
    "task": "Open /home/user/Documents/clipmask.svg. The file has two groups of colorful rectangles ('grid' and 'grid2') plus a circle 'clipShape' and a white rectangle 'maskShape'.\n\n1. CLIP the 'grid' group using 'clipShape' (circular clip). The 'grid' element id must be preserved and it must gain a clip-path attribute referencing the clip.\n2. MASK the 'grid2' group using 'maskShape' so it appears partially transparent. The 'grid2' element must gain a mask attribute referencing the mask.\n\nSave /home/user/Documents/clipmask.svg in place.",
    "env": {"files": [{"filename": "clipmask.svg", "sandbox_path": "/home/user/Documents/clipmask.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/clipmask.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/clipmask.svg grid", "key": "exists", "expected": True, "description": "grid preserved"},
        {"command": "check-element-exists /home/user/Documents/clipmask.svg grid2", "key": "exists", "expected": True, "description": "grid2 preserved"},
        {"command": "check-text-contains /home/user/Documents/clipmask.svg clipPath", "key": "contains", "expected": True, "description": "clipPath defined"},
        {"command": "check-text-contains /home/user/Documents/clipmask.svg clip-path", "key": "contains", "expected": True, "description": "clip-path attribute used"},
        {"command": "check-text-contains /home/user/Documents/clipmask.svg mask", "key": "contains", "expected": True, "description": "mask construct present"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"clipmask.svg": svg3}, tasks[-1])

# -------------------- Task 4: linear + radial gradients --------------------
svg4 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="600" height="300" viewBox="0 0 600 300">
  <rect id="rectL" x="40" y="60" width="220" height="180" fill="#888888"/>
  <circle id="circR" cx="430" cy="150" r="100" fill="#888888"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_linear_radial_gradients",
    "app": "inkscape",
    "task": "Open /home/user/Documents/gradients.svg. Replace the solid fills with gradients:\n\n1. rectL: a LINEAR gradient from #ff0000 at offset 0 to #0000ff at offset 1, running left to right (horizontal).\n2. circR: a RADIAL gradient from #ffff00 at the center to #000088 at the edge.\n\nThe gradient definitions must live under <defs>. Save /home/user/Documents/gradients.svg in place.",
    "env": {"files": [{"filename": "gradients.svg", "sandbox_path": "/home/user/Documents/gradients.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/gradients.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/gradients.svg rectL", "key": "exists", "expected": True, "description": "rectL preserved"},
        {"command": "check-element-exists /home/user/Documents/gradients.svg circR", "key": "exists", "expected": True, "description": "circR preserved"},
        {"command": "check-text-contains /home/user/Documents/gradients.svg linearGradient", "key": "contains", "expected": True, "description": "Linear gradient defined"},
        {"command": "check-text-contains /home/user/Documents/gradients.svg radialGradient", "key": "contains", "expected": True, "description": "Radial gradient defined"},
        {"command": "check-text-contains /home/user/Documents/gradients.svg ff0000", "key": "contains", "expected": True, "description": "Red stop present"},
        {"command": "check-text-contains /home/user/Documents/gradients.svg 0000ff", "key": "contains", "expected": True, "description": "Blue stop present"},
        {"command": "check-text-contains /home/user/Documents/gradients.svg ffff00", "key": "contains", "expected": True, "description": "Yellow stop present"},
        {"command": "check-text-contains /home/user/Documents/gradients.svg 000088", "key": "contains", "expected": True, "description": "Dark blue stop present"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"gradients.svg": svg4}, tasks[-1])

# -------------------- Task 5: filter blur + dropshadow --------------------
svg5 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="700" height="300" viewBox="0 0 700 300">
  <text id="title" x="60" y="90" font-size="48" font-family="sans-serif" fill="#222266">Synth Demo</text>
  <rect id="card" x="60" y="140" width="320" height="120" fill="#f0c040" stroke="#000000" stroke-width="2"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_filter_blur_dropshadow",
    "app": "inkscape",
    "task": "Open /home/user/Documents/filters.svg. Apply two SVG filters:\n\n1. Apply a GAUSSIAN BLUR filter with stdDeviation of 4 to the text element 'title'.\n2. Apply a DROP SHADOW filter to the rectangle 'card' (offset approximately 6,6; blur radius around 3; shadow color #000000 at roughly 50 percent opacity).\n\nEach element must have a 'filter' attribute referencing a defined <filter> in <defs>. Save /home/user/Documents/filters.svg in place.",
    "env": {"files": [{"filename": "filters.svg", "sandbox_path": "/home/user/Documents/filters.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/filters.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/filters.svg title", "key": "exists", "expected": True, "description": "title preserved"},
        {"command": "check-element-exists /home/user/Documents/filters.svg card", "key": "exists", "expected": True, "description": "card preserved"},
        {"command": "check-text-contains /home/user/Documents/filters.svg feGaussianBlur", "key": "contains", "expected": True, "description": "Gaussian blur primitive present"},
        {"command": "check-text-contains /home/user/Documents/filters.svg feOffset", "key": "contains", "expected": True, "description": "feOffset (drop shadow) present"},
        {"command": "check-text-contains /home/user/Documents/filters.svg filter", "key": "contains", "expected": True, "description": "filter reference present"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"filters.svg": svg5}, tasks[-1])

# -------------------- Task 6: markers / arrows --------------------
svg6 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="600" height="400" viewBox="0 0 600 400">
  <polyline id="arr1" points="40,60 180,60 260,120" fill="none" stroke="#222222" stroke-width="3"/>
  <polyline id="arr2" points="40,160 180,160 260,220" fill="none" stroke="#222222" stroke-width="3"/>
  <polyline id="arr3" points="40,260 180,260 260,320" fill="none" stroke="#222222" stroke-width="3"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_markers_arrows",
    "app": "inkscape",
    "task": "Open /home/user/Documents/markers.svg. Add an end-arrow MARKER to each of the three polylines (arr1, arr2, arr3):\n- arr1 must use a TRIANGLE marker defined as <marker id='arrowTri' ...> in <defs>.\n- arr2 must use a DOT/CIRCLE marker defined as <marker id='arrowDot' ...>.\n- arr3 must use a DIAMOND marker defined as <marker id='arrowDia' ...>.\n\nEach polyline should have marker-end='url(#arrowTri|arrowDot|arrowDia)' as appropriate. Save /home/user/Documents/markers.svg in place.",
    "env": {"files": [{"filename": "markers.svg", "sandbox_path": "/home/user/Documents/markers.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/markers.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/markers.svg arrowTri", "key": "exists", "expected": True, "description": "Triangle marker defined"},
        {"command": "check-element-exists /home/user/Documents/markers.svg arrowDot", "key": "exists", "expected": True, "description": "Dot marker defined"},
        {"command": "check-element-exists /home/user/Documents/markers.svg arrowDia", "key": "exists", "expected": True, "description": "Diamond marker defined"},
        {"command": "check-text-contains /home/user/Documents/markers.svg marker-end", "key": "contains", "expected": True, "description": "marker-end attribute used"},
        {"command": "check-text-contains /home/user/Documents/markers.svg arrowTri", "key": "contains", "expected": True, "description": "arrowTri referenced"},
        {"command": "check-text-contains /home/user/Documents/markers.svg arrowDot", "key": "contains", "expected": True, "description": "arrowDot referenced"},
        {"command": "check-text-contains /home/user/Documents/markers.svg arrowDia", "key": "contains", "expected": True, "description": "arrowDia referenced"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"markers.svg": svg6}, tasks[-1])

# -------------------- Task 7: text on path --------------------
svg7 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="800" height="300" viewBox="0 0 800 300">
  <path id="wavePath" d="M 40,180 C 140,40 240,320 340,180 C 440,40 540,320 640,180 C 700,100 760,100 780,180" fill="none" stroke="#888888" stroke-width="1"/>
  <text id="labelText" font-family="sans-serif" font-size="28" fill="#223366" x="40" y="260">INKSCAPE CURVE RIDE</text>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_text_on_path",
    "app": "inkscape",
    "task": "Open /home/user/Documents/textpath.svg. It contains a wavy path 'wavePath' and a text element 'labelText' reading 'INKSCAPE CURVE RIDE'. Put the text onto the path so it renders along the wave (SVG <textPath> with xlink:href='#wavePath'). Keep the text content exactly 'INKSCAPE CURVE RIDE'. Save /home/user/Documents/textpath.svg in place.",
    "env": {"files": [{"filename": "textpath.svg", "sandbox_path": "/home/user/Documents/textpath.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/textpath.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/textpath.svg wavePath", "key": "exists", "expected": True, "description": "wavePath preserved"},
        {"command": "check-element-exists /home/user/Documents/textpath.svg labelText", "key": "exists", "expected": True, "description": "labelText preserved"},
        {"command": "check-text-contains /home/user/Documents/textpath.svg textPath", "key": "contains", "expected": True, "description": "textPath element present"},
        {"command": "check-text-contains /home/user/Documents/textpath.svg wavePath", "key": "contains", "expected": True, "description": "wavePath referenced"},
        {"command": "check-text-contains /home/user/Documents/textpath.svg INKSCAPE", "key": "contains", "expected": True, "description": "Label text present"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"textpath.svg": svg7}, tasks[-1])

# -------------------- Task 8: pattern fill --------------------
svg8 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="500" height="400" viewBox="0 0 500 400">
  <rect id="bg" x="40" y="40" width="420" height="320" fill="#888888"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_pattern_fill",
    "app": "inkscape",
    "task": "Open /home/user/Documents/pattern.svg. Create a PATTERN with id 'dotsPattern' consisting of a 20x20 tile with a single blue circle in the middle. Fill the rectangle 'bg' with that pattern (fill='url(#dotsPattern)'). The pattern must be defined inside <defs>. Save /home/user/Documents/pattern.svg in place.",
    "env": {"files": [{"filename": "pattern.svg", "sandbox_path": "/home/user/Documents/pattern.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/pattern.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/pattern.svg bg", "key": "exists", "expected": True, "description": "bg preserved"},
        {"command": "check-element-exists /home/user/Documents/pattern.svg dotsPattern", "key": "exists", "expected": True, "description": "dotsPattern defined"},
        {"command": "check-text-contains /home/user/Documents/pattern.svg pattern", "key": "contains", "expected": True, "description": "Pattern element present"},
        {"command": "check-text-contains /home/user/Documents/pattern.svg dotsPattern", "key": "contains", "expected": True, "description": "dotsPattern referenced"},
        {"command": "check-style-property /home/user/Documents/pattern.svg bg fill url(#dotsPattern)", "key": "match", "expected": True, "description": "bg fill uses pattern"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"pattern.svg": svg8}, tasks[-1])

# -------------------- Task 9: LPE pattern along path --------------------
svg9 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="700" height="300" viewBox="0 0 700 300">
  <path id="spine" d="M 40,150 L 120,80 L 200,220 L 280,80 L 360,220 L 440,80 L 520,220 L 600,150" fill="none" stroke="#222244" stroke-width="2"/>
  <path id="ornament" d="M 40,260 L 60,280 L 20,280 Z" fill="#cc3344" stroke="#220000"/>
</svg>
'''
tasks.append({
    "id": "inkscape_gap_path_effect_pattern_along_path",
    "app": "inkscape",
    "task": "Open /home/user/Documents/lpe_pap.svg. Apply Inkscape's Live Path Effect 'Pattern Along Path' to the 'spine' path, using the small 'ornament' triangle as the pattern source so the triangle is tiled along the spine. After applying the effect, ensure the SVG contains an <inkscape:path-effect effect='skeletal' ...> element inside <defs>, and that the 'spine' path has an inkscape:path-effect attribute referencing that effect. Save /home/user/Documents/lpe_pap.svg in place.",
    "env": {"files": [{"filename": "lpe_pap.svg", "sandbox_path": "/home/user/Documents/lpe_pap.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/lpe_pap.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/lpe_pap.svg spine", "key": "exists", "expected": True, "description": "spine preserved"},
        {"command": "check-text-contains /home/user/Documents/lpe_pap.svg path-effect", "key": "contains", "expected": True, "description": "inkscape:path-effect present"},
        {"command": "check-text-contains /home/user/Documents/lpe_pap.svg skeletal", "key": "contains", "expected": True, "description": "Pattern Along Path effect id is skeletal"}
    ],
    "metadata": {"complexity": 5, "data_generatability": 5, "estimated_difficulty": 5}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"lpe_pap.svg": svg9}, tasks[-1])

# -------------------- Task 10: symbols library --------------------
svg10 = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg {SVG_NS} width="700" height="400" viewBox="0 0 700 400">
  <!-- Empty scaffold; agent will build symbols and uses -->
</svg>
'''
tasks.append({
    "id": "inkscape_gap_symbols_library",
    "app": "inkscape",
    "task": "Open /home/user/Documents/symbols.svg (currently an empty canvas). Build a reusable symbol library:\n\n1. Define two <symbol> elements inside <defs>:\n   - symbol id='sGear' — an 8-tooth cog / gear shape (approximation is fine).\n   - symbol id='sStar' — a 5-point star.\n2. Instantiate each symbol THREE times using <use> elements, at different positions with different scales. So the final document must contain at least six <use> elements, three referencing #sGear and three referencing #sStar.\n\nSave /home/user/Documents/symbols.svg in place.",
    "env": {"files": [{"filename": "symbols.svg", "sandbox_path": "/home/user/Documents/symbols.svg"}]},
    "verification": [
        {"command": "check-file-exists /home/user/Documents/symbols.svg", "key": "exists", "expected": True, "description": "File saved"},
        {"command": "check-element-exists /home/user/Documents/symbols.svg sGear", "key": "exists", "expected": True, "description": "Gear symbol defined"},
        {"command": "check-element-exists /home/user/Documents/symbols.svg sStar", "key": "exists", "expected": True, "description": "Star symbol defined"},
        {"command": "check-text-contains /home/user/Documents/symbols.svg symbol", "key": "contains", "expected": True, "description": "symbol elements exist"},
        {"command": "check-text-contains /home/user/Documents/symbols.svg sGear", "key": "contains", "expected": True, "description": "Gear referenced"},
        {"command": "check-text-contains /home/user/Documents/symbols.svg sStar", "key": "contains", "expected": True, "description": "Star referenced"},
        {"command": "elements /home/user/Documents/symbols.svg", "eval": "sum(1 for e in result if e.get('tag') == 'use' and 'sGear' in (e.get('href') or e.get('xlink:href') or '')) >= 3", "expected": True, "description": "At least 3 uses of sGear"},
        {"command": "elements /home/user/Documents/symbols.svg", "eval": "sum(1 for e in result if e.get('tag') == 'use' and 'sStar' in (e.get('href') or e.get('xlink:href') or '')) >= 3", "expected": True, "description": "At least 3 uses of sStar"}
    ],
    "metadata": {"complexity": 4, "data_generatability": 5, "estimated_difficulty": 4}
})
write_task(tasks[-1]["id"], tasks[-1]["env"]["files"], {"symbols.svg": svg10}, tasks[-1])

# ---- write combined ----
combined_path = ROOT / "inkscape_tasks.json"
existing = []
if combined_path.exists():
    try:
        existing = json.loads(combined_path.read_text())
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []
# Remove any existing entries for these IDs then append
new_ids = {t["id"] for t in tasks}
existing = [t for t in existing if t.get("id") not in new_ids]
existing.extend(tasks)
combined_path.write_text(json.dumps(existing, indent=2))

print(f"Generated {len(tasks)} Inkscape gap tasks. Combined file has {len(existing)} total.")
