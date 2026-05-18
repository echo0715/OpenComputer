"""
Env generator for the 3 harder musescore3 tasks:
  - musescore3_two_voice_counterpoint:   8-bar C maj 4/4, voice 1 quarter notes, empty voice 2
  - musescore3_compose_16bar_leadsheet:  16-bar G maj 3/4 scaffold with whole-measure rests only
  - musescore3_piano_to_string_quartet:  4-bar C maj 4/4 piano, 4 quarter notes per measure

Each fixture is a valid .mscz (zip of META-INF/container.xml + inner .mscx) that
mscore3 opens without warnings. Generator runs fully offline — stdlib only.

Run:
    python3 task_generator/tasks/_musescore3_gen_env_harder.py
"""

import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).parent

# C major natural-note TPC lookup for pitches % 12 (naturals only)
TPC_NATURAL = {0: 14, 2: 16, 4: 18, 5: 13, 7: 15, 9: 17, 11: 19}


def tpc_for(pitch: int) -> int:
    return TPC_NATURAL.get(pitch % 12, 14)


def _c_major_scale(start: int, count: int) -> list[int]:
    naturals = [0, 2, 4, 5, 7, 9, 11]
    out, octave = [], 0
    base_octave = start // 12
    # snap start up to nearest natural
    s = start
    while s % 12 not in naturals:
        s += 1
    while len(out) < count:
        for n in naturals:
            if len(out) >= count:
                break
            p = (base_octave + octave) * 12 + n
            if p >= s:
                out.append(p)
        octave += 1
    return out


# ---------------------------------------------------------------------------
# Common mscx scaffolding
# ---------------------------------------------------------------------------

def _meta_block(work_title: str = "Untitled Score", composer: str = "",
                copyright_: str = "", arranger: str = "",
                lyricist: str = "") -> str:
    return f"""  <metaTag name="arranger">{arranger}</metaTag>
  <metaTag name="composer">{composer}</metaTag>
  <metaTag name="copyright">{copyright_}</metaTag>
  <metaTag name="creationDate">2024-01-01</metaTag>
  <metaTag name="lyricist">{lyricist}</metaTag>
  <metaTag name="movementNumber"></metaTag>
  <metaTag name="movementTitle"></metaTag>
  <metaTag name="platform">Linux</metaTag>
  <metaTag name="poet"></metaTag>
  <metaTag name="source"></metaTag>
  <metaTag name="translator"></metaTag>
  <metaTag name="workNumber"></metaTag>
  <metaTag name="workTitle">{work_title}</metaTag>
"""


def _part_block(idx: int, long_name: str, short_name: str, instrument_id: str,
                min_pitch_p: int = 21, max_pitch_p: int = 108,
                min_pitch_a: int | None = None, max_pitch_a: int | None = None,
                program: int = 0, clef: str = "G") -> str:
    if min_pitch_a is None:
        min_pitch_a = min_pitch_p
    if max_pitch_a is None:
        max_pitch_a = max_pitch_p
    return f"""  <Part>
   <Staff id="{idx + 1}">
    <StaffType group="pitched">
     <name>stdNormal</name>
    </StaffType>
   </Staff>
   <trackName>{long_name}</trackName>
   <Instrument>
    <longName>{long_name}</longName>
    <shortName>{short_name}</shortName>
    <trackName>{long_name}</trackName>
    <minPitchP>{min_pitch_p}</minPitchP>
    <maxPitchP>{max_pitch_p}</maxPitchP>
    <minPitchA>{min_pitch_a}</minPitchA>
    <maxPitchA>{max_pitch_a}</maxPitchA>
    <instrumentId>{instrument_id}</instrumentId>
    <Channel>
     <program value="{program}"/>
     <synti>Fluid</synti>
    </Channel>
   </Instrument>
  </Part>
"""


def _header_measure_prefix(time_n: int, time_d: int, key_acc: int, bpm: int) -> str:
    """First-measure prefix with TimeSig, KeySig, and Tempo."""
    bps = bpm / 60.0
    return (
        f"<TimeSig><sigN>{time_n}</sigN><sigD>{time_d}</sigD></TimeSig>"
        f"<KeySig><accidental>{key_acc}</accidental></KeySig>"
        f"<Tempo><tempo>{bps}</tempo><followText>1</followText>"
        f"<text><sym>metNoteQuarterUp</sym> = {bpm}</text></Tempo>"
    )


def _wrap_mscx(meta_xml: str, parts_xml: str, staves_xml: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<museScore version="3.01">
 <programVersion>3.6.2</programVersion>
 <programRevision>3224f34</programRevision>
 <Score>
  <LayerTag id="0" tag="default"></LayerTag>
  <currentLayer>0</currentLayer>
  <Division>480</Division>
  <Style>
   <pageWidth>8.5</pageWidth>
   <pageHeight>11</pageHeight>
  </Style>
  <showInvisible>1</showInvisible>
  <showUnprintable>1</showUnprintable>
  <showFrames>1</showFrames>
  <showMargins>0</showMargins>
{meta_xml}{parts_xml}{staves_xml} </Score>
</museScore>
"""


def _write_mscz(out_path: Path, mscx: str, inner_name: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    container = f"""<?xml version="1.0" encoding="UTF-8"?>
<container>
 <rootfiles>
  <rootfile full-path="{inner_name}"/>
 </rootfiles>
</container>
"""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", container)
        zf.writestr(inner_name, mscx)


# ---------------------------------------------------------------------------
# Fixture 1: counterpoint_study.mscz
#   8 measures in C major 4/4 on one piano staff
#   Voice 1: 4 quarter notes per measure (32 notes total), C major scale cycle
#   Voice 2: empty (no notes — note input will add them later)
# ---------------------------------------------------------------------------

def build_counterpoint_study() -> str:
    time_n, time_d, key_acc, bpm = 4, 4, 0, 100
    measures = 8
    notes_per_m = 4

    scale = _c_major_scale(start=60, count=measures * notes_per_m)  # C4..
    measure_list = []
    idx = 0
    for m in range(measures):
        voice_content = ""
        if m == 0:
            voice_content += _header_measure_prefix(time_n, time_d, key_acc, bpm)
        for _ in range(notes_per_m):
            p = scale[idx]; idx += 1
            voice_content += (
                f"<Chord><durationType>quarter</durationType>"
                f"<Note><pitch>{p}</pitch><tpc>{tpc_for(p)}</tpc></Note></Chord>"
            )
        measure_list.append(f"    <Measure><voice>{voice_content}</voice></Measure>")

    staves_xml = (
        '  <Staff id="1">\n' + "\n".join(measure_list) + "\n  </Staff>\n"
    )
    return _wrap_mscx(
        meta_xml=_meta_block(work_title="Counterpoint Study", composer=""),
        parts_xml=_part_block(0, "Piano", "Pno.", "keyboard.piano"),
        staves_xml=staves_xml,
    )


# ---------------------------------------------------------------------------
# Fixture 2: moonlight_scaffold.mscz
#   16 measures in G major 3/4 on one piano staff, whole-measure rests only
#   Tempo = 90 BPM, no composer, workTitle = "Untitled Score"
# ---------------------------------------------------------------------------

def build_moonlight_scaffold() -> str:
    time_n, time_d, key_acc, bpm = 3, 4, 1, 90  # G major
    measures = 16

    measure_list = []
    for m in range(measures):
        voice_content = ""
        if m == 0:
            voice_content += _header_measure_prefix(time_n, time_d, key_acc, bpm)
        # Whole-measure rest in 3/4 = dotted-half rest (but we use <Rest> with
        # durationType="measure" which MuseScore handles for any time signature)
        voice_content += '<Rest><durationType>measure</durationType><duration>3/4</duration></Rest>'
        measure_list.append(f"    <Measure><voice>{voice_content}</voice></Measure>")

    staves_xml = (
        '  <Staff id="1">\n' + "\n".join(measure_list) + "\n  </Staff>\n"
    )
    return _wrap_mscx(
        meta_xml=_meta_block(work_title="Untitled Score", composer=""),
        parts_xml=_part_block(0, "Piano", "Pno.", "keyboard.piano"),
        staves_xml=staves_xml,
    )


# ---------------------------------------------------------------------------
# Fixture 3: piano_sketch.mscz
#   4 measures in C major 4/4, 4 quarter notes per measure, on one piano staff
# ---------------------------------------------------------------------------

def build_piano_sketch() -> str:
    time_n, time_d, key_acc, bpm = 4, 4, 0, 108
    measures = 4
    notes_per_m = 4

    scale = _c_major_scale(start=60, count=measures * notes_per_m)
    measure_list = []
    idx = 0
    for m in range(measures):
        voice_content = ""
        if m == 0:
            voice_content += _header_measure_prefix(time_n, time_d, key_acc, bpm)
        for _ in range(notes_per_m):
            p = scale[idx]; idx += 1
            voice_content += (
                f"<Chord><durationType>quarter</durationType>"
                f"<Note><pitch>{p}</pitch><tpc>{tpc_for(p)}</tpc></Note></Chord>"
            )
        measure_list.append(f"    <Measure><voice>{voice_content}</voice></Measure>")

    staves_xml = (
        '  <Staff id="1">\n' + "\n".join(measure_list) + "\n  </Staff>\n"
    )
    return _wrap_mscx(
        meta_xml=_meta_block(work_title="Piano Sketch", composer=""),
        parts_xml=_part_block(0, "Piano", "Pno.", "keyboard.piano"),
        staves_xml=staves_xml,
    )


# ---------------------------------------------------------------------------
# Fixture verification helpers
# ---------------------------------------------------------------------------

def _inner_mscx(path: Path) -> bytes:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        assert "META-INF/container.xml" in names, f"no container.xml in {path}"
        inner = [n for n in names if n.endswith(".mscx")]
        assert inner, f"no .mscx in {path}"
        return zf.read(inner[0])


def _count_notes(root: ET.Element) -> int:
    return sum(1 for e in root.iter() if e.tag == "Note")


def _count_parts(root: ET.Element) -> int:
    return sum(1 for e in root.iter() if e.tag == "Part")


def _count_measures(root: ET.Element) -> int:
    # Measures live in the top-level <Score>/<Staff id="1"> (not the per-Part
    # <Staff> that defines the StaffType). Pick the Staff whose direct
    # children include at least one Measure.
    for staff in root.iter("Staff"):
        measures = [c for c in staff if c.tag == "Measure"]
        if measures:
            return len(measures)
    return 0


def _first_time_sig(root: ET.Element) -> tuple[int, int] | None:
    for ts in root.iter("TimeSig"):
        sigN = ts.findtext("sigN")
        sigD = ts.findtext("sigD")
        if sigN and sigD:
            return int(sigN), int(sigD)
    return None


def _first_key_sig(root: ET.Element) -> int | None:
    for ks in root.iter("KeySig"):
        acc = ks.findtext("accidental")
        if acc is not None:
            return int(acc)
    return None


def _first_tempo_bpm(root: ET.Element) -> float | None:
    for t in root.iter("Tempo"):
        tempo = t.findtext("tempo")
        if tempo is not None:
            return float(tempo) * 60.0
    return None


def _work_title(root: ET.Element) -> str | None:
    for mt in root.iter("metaTag"):
        if mt.get("name") == "workTitle":
            return mt.text or ""
    return None


def verify_fixture(path: Path, expected: dict) -> None:
    data = _inner_mscx(path)
    root = ET.fromstring(data)

    if "measures" in expected:
        actual = _count_measures(root)
        assert actual == expected["measures"], f"{path.name}: measures {actual} != {expected['measures']}"
    if "notes" in expected:
        actual = _count_notes(root)
        assert actual == expected["notes"], f"{path.name}: notes {actual} != {expected['notes']}"
    if "parts" in expected:
        actual = _count_parts(root)
        assert actual == expected["parts"], f"{path.name}: parts {actual} != {expected['parts']}"
    if "time_sig" in expected:
        actual = _first_time_sig(root)
        assert actual == expected["time_sig"], f"{path.name}: time_sig {actual} != {expected['time_sig']}"
    if "key_sig" in expected:
        actual = _first_key_sig(root)
        assert actual == expected["key_sig"], f"{path.name}: key_sig {actual} != {expected['key_sig']}"
    if "tempo_bpm" in expected:
        actual = _first_tempo_bpm(root)
        assert actual is not None and abs(actual - expected["tempo_bpm"]) < 0.5, \
            f"{path.name}: tempo {actual} != {expected['tempo_bpm']}"
    if "work_title" in expected:
        actual = _work_title(root)
        assert actual == expected["work_title"], f"{path.name}: workTitle {actual!r} != {expected['work_title']!r}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SPECS = [
    {
        "task_id": "musescore3_two_voice_counterpoint",
        "filename": "counterpoint_study.mscz",
        "sandbox_path": "/home/user/Documents/counterpoint_study.mscz",
        "builder": build_counterpoint_study,
        "expected": {
            "measures": 8,
            "notes": 32,
            "parts": 1,
            "time_sig": (4, 4),
            "key_sig": 0,
            "tempo_bpm": 100.0,
            "work_title": "Counterpoint Study",
        },
    },
    {
        "task_id": "musescore3_compose_16bar_leadsheet",
        "filename": "moonlight_scaffold.mscz",
        "sandbox_path": "/home/user/Documents/moonlight_scaffold.mscz",
        "builder": build_moonlight_scaffold,
        "expected": {
            "measures": 16,
            "notes": 0,
            "parts": 1,
            "time_sig": (3, 4),
            "key_sig": 1,
            "tempo_bpm": 90.0,
            "work_title": "Untitled Score",
        },
    },
    {
        "task_id": "musescore3_piano_to_string_quartet",
        "filename": "piano_sketch.mscz",
        "sandbox_path": "/home/user/Documents/piano_sketch.mscz",
        "builder": build_piano_sketch,
        "expected": {
            "measures": 4,
            "notes": 16,
            "parts": 1,
            "time_sig": (4, 4),
            "key_sig": 0,
            "tempo_bpm": 108.0,
            "work_title": "Piano Sketch",
        },
    },
]


def main() -> None:
    for spec in SPECS:
        task_dir = BASE / spec["task_id"]
        env_dir = task_dir / "env"
        env_dir.mkdir(parents=True, exist_ok=True)

        out_path = env_dir / spec["filename"]
        inner_name = spec["filename"].replace(".mscz", ".mscx")
        mscx = spec["builder"]()
        _write_mscz(out_path, mscx, inner_name=inner_name)

        # Verify it parses and matches expectations
        verify_fixture(out_path, spec["expected"])

        manifest = {
            "task_id": spec["task_id"],
            "files": [
                {
                    "filename": spec["filename"],
                    "sandbox_path": spec["sandbox_path"],
                    "type": "mscz",
                }
            ],
        }
        with open(task_dir / "env_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes) — verified {spec['expected']}")

    print(f"\nGenerated {len(SPECS)} harder-musescore3 fixtures.")


if __name__ == "__main__":
    main()
