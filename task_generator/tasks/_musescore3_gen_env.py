"""
Generator for all musescore3 task env files.

Produces real `.mscz` files that MuseScore 3.6 opens cleanly (verified against
mscore3 headless conversion in an E2B sandbox).

Run:
    python3 task_generator/tasks/_musescore3_gen_env.py

Files land in task_generator/tasks/<task_id>/env/.
"""

import os
import zipfile
from pathlib import Path

# C major natural-note TPC lookup (MuseScore tonal pitch class) for pitches % 12
TPC_NATURAL = {0: 14, 2: 16, 4: 18, 5: 13, 7: 15, 9: 17, 11: 19}


def tpc_for(pitch: int) -> int:
    n = pitch % 12
    return TPC_NATURAL.get(n, 14)


def natural_scale_pitches(start=60, count=8):
    """Generate `count` ascending natural (C major) pitches starting at or above `start`."""
    naturals = [0, 2, 4, 5, 7, 9, 11]
    out = []
    p = start
    # snap to nearest natural at or above start
    while p % 12 not in naturals:
        p += 1
    octave = 0
    while len(out) < count:
        for n in naturals:
            if len(out) >= count:
                break
            candidate = (p // 12 + octave) * 12 + n
            if candidate >= p:
                out.append(candidate)
        octave += 1
    return out


def build_mscx(
    title: str = "Untitled",
    composer: str = "",
    copyright_: str = "",
    arranger: str = "",
    lyricist: str = "",
    time_n: int = 4,
    time_d: int = 4,
    key_acc: int = 0,
    bps: float = 2.0,
    parts=None,
    measures: int = 4,
    notes_per_measure: int = 3,
    lyrics: bool = False,
) -> str:
    """Build a MuseScore 3.01-compatible .mscx string.

    Parameters correspond to initial state of the score. Lyrics, when True, attach
    3 lyric syllables to the first 3 notes of the first staff (words "hel-lo-world").
    """
    if parts is None:
        parts = [("Piano", "Pno.", "keyboard.piano")]

    part_xml = ""
    for i, (ln, sn, iid) in enumerate(parts):
        part_xml += f"""  <Part>
   <Staff id="{i + 1}">
    <StaffType group="pitched">
     <name>stdNormal</name>
    </StaffType>
   </Staff>
   <trackName>{ln}</trackName>
   <Instrument>
    <longName>{ln}</longName>
    <shortName>{sn}</shortName>
    <trackName>{ln}</trackName>
    <minPitchP>21</minPitchP>
    <maxPitchP>108</maxPitchP>
    <minPitchA>21</minPitchA>
    <maxPitchA>108</maxPitchA>
    <instrumentId>{iid}</instrumentId>
    <Channel>
     <program value="0"/>
     <synti>Fluid</synti>
    </Channel>
   </Instrument>
  </Part>
"""

    staff_xml = ""
    for staff_index in range(len(parts)):
        scale = natural_scale_pitches(start=60 - staff_index * 12, count=measures * notes_per_measure)
        idx = 0
        measure_list = []
        for m in range(measures):
            voice_content = ""
            if m == 0:
                voice_content += f"<TimeSig><sigN>{time_n}</sigN><sigD>{time_d}</sigD></TimeSig>"
                voice_content += f"<KeySig><accidental>{key_acc}</accidental></KeySig>"
                bpm_int = max(1, int(round(bps * 60)))
                voice_content += (
                    f"<Tempo><tempo>{bps}</tempo><followText>1</followText>"
                    f"<text><sym>metNoteQuarterUp</sym> = {bpm_int}</text></Tempo>"
                )
            for _ in range(notes_per_measure):
                pitch = scale[idx]
                idx += 1
                lyric_xml = ""
                if lyrics and staff_index == 0 and m == 0 and idx <= 3:
                    syl_word = ["hel", "lo", "world"][idx - 1]
                    syl_type = ["begin", "middle", "end"][idx - 1]
                    lyric_xml = f"<Lyrics><text>{syl_word}</text><syllabic>{syl_type}</syllabic></Lyrics>"
                voice_content += (
                    f"<Chord><durationType>quarter</durationType>{lyric_xml}"
                    f"<Note><pitch>{pitch}</pitch><tpc>{tpc_for(pitch)}</tpc></Note></Chord>"
                )
            measure_list.append(f"    <Measure><voice>{voice_content}</voice></Measure>")
        staff_xml += f'  <Staff id="{staff_index + 1}">\n' + "\n".join(measure_list) + "\n  </Staff>\n"

    mscx = f"""<?xml version="1.0" encoding="UTF-8"?>
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
  <metaTag name="arranger">{arranger}</metaTag>
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
  <metaTag name="workTitle">{title}</metaTag>
{part_xml}{staff_xml} </Score>
</museScore>
"""
    return mscx


def write_mscz(out_path: Path, mscx: str, inner_name: str = "score.mscx") -> None:
    """Write a valid .mscz with META-INF/container.xml + inner .mscx."""
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
# Per-task fixture specs
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent

SPECS = [
    # musescore3_set_score_metadata — initial metadata is placeholder values
    {
        "task_id": "musescore3_set_score_metadata",
        "filename": "prelude.mscz",
        "sandbox_path": "/home/user/Documents/prelude.mscz",
        "kwargs": dict(
            title="Untitled Score",
            composer="Anonymous",
            copyright_="",
            measures=4,
            notes_per_measure=4,
            bps=2.0,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
    # musescore3_change_tempo_marking — initial 90 BPM (= 1.5 bps)
    {
        "task_id": "musescore3_change_tempo_marking",
        "filename": "allegretto.mscz",
        "sandbox_path": "/home/user/Documents/allegretto.mscz",
        "kwargs": dict(
            title="Allegretto",
            composer="Test",
            bps=1.5,  # 90 BPM
            measures=8,
            notes_per_measure=4,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
    # musescore3_change_time_signature — initial 4/4
    {
        "task_id": "musescore3_change_time_signature",
        "filename": "waltz_sketch.mscz",
        "sandbox_path": "/home/user/Documents/waltz_sketch.mscz",
        "kwargs": dict(
            title="Waltz Sketch",
            composer="Test",
            bps=2.0,
            measures=4,
            notes_per_measure=4,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
    # musescore3_transpose_to_g_major — initial key 0 (C major)
    {
        "task_id": "musescore3_transpose_to_g_major",
        "filename": "etude_c.mscz",
        "sandbox_path": "/home/user/Documents/etude_c.mscz",
        "kwargs": dict(
            title="C Major Etude",
            composer="Test",
            bps=2.0,
            measures=4,
            notes_per_measure=4,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
    # musescore3_add_lyrics_to_melody — single melody staff, no initial lyrics
    {
        "task_id": "musescore3_add_lyrics_to_melody",
        "filename": "melody.mscz",
        "sandbox_path": "/home/user/Documents/melody.mscz",
        "kwargs": dict(
            title="Simple Melody",
            composer="Test",
            bps=2.0,
            measures=2,
            notes_per_measure=4,
            key_acc=0,
            time_n=4, time_d=4,
            lyrics=False,
        ),
    },
    # musescore3_export_midi
    {
        "task_id": "musescore3_export_midi",
        "filename": "dance.mscz",
        "sandbox_path": "/home/user/Documents/dance.mscz",
        "kwargs": dict(
            title="Simple Dance",
            composer="Test",
            bps=2.0,
            measures=4,
            notes_per_measure=4,
            key_acc=0,
            time_n=3, time_d=4,
        ),
    },
    # musescore3_export_musicxml — needs 2 parts
    {
        "task_id": "musescore3_export_musicxml",
        "filename": "duet.mscz",
        "sandbox_path": "/home/user/Documents/duet.mscz",
        "kwargs": dict(
            title="Little Duet",
            composer="Test",
            bps=2.0,
            measures=4,
            notes_per_measure=3,
            key_acc=0,
            time_n=4, time_d=4,
            parts=[
                ("Flute", "Fl.", "wind.flutes.flute"),
                ("Cello", "Vc.", "strings.cello"),
            ],
        ),
    },
    # musescore3_export_pdf
    {
        "task_id": "musescore3_export_pdf",
        "filename": "sonatina.mscz",
        "sandbox_path": "/home/user/Documents/sonatina.mscz",
        "kwargs": dict(
            title="Sonatina",
            composer="Test",
            bps=2.0,
            measures=4,
            notes_per_measure=4,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
    # musescore3_set_autosave_interval — placeholder file so the app launches with a doc
    {
        "task_id": "musescore3_set_autosave_interval",
        "filename": "placeholder.mscz",
        "sandbox_path": "/home/user/Documents/placeholder.mscz",
        "kwargs": dict(
            title="Placeholder",
            composer="",
            measures=2,
            notes_per_measure=2,
            bps=2.0,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
    # musescore3_add_composer_and_export_all
    {
        "task_id": "musescore3_add_composer_and_export_all",
        "filename": "fanfare.mscz",
        "sandbox_path": "/home/user/Documents/fanfare.mscz",
        "kwargs": dict(
            title="Fanfare",
            composer="Anonymous",
            bps=2.0,
            measures=4,
            notes_per_measure=4,
            key_acc=0,
            time_n=4, time_d=4,
        ),
    },
]


def main() -> None:
    import json

    for spec in SPECS:
        task_dir = BASE / spec["task_id"]
        env_dir = task_dir / "env"
        env_dir.mkdir(parents=True, exist_ok=True)
        out_path = env_dir / spec["filename"]
        mscx = build_mscx(**spec["kwargs"])
        write_mscz(out_path, mscx, inner_name=spec["filename"].replace(".mscz", ".mscx"))
        # Verify the zip parses and the inner mscx is valid XML
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            assert "META-INF/container.xml" in names, f"no container.xml in {out_path}"
            inner = [n for n in names if n.endswith(".mscx")]
            assert inner, f"no .mscx in {out_path}"
            data = zf.read(inner[0])
            ET.fromstring(data)  # parses
        # Write manifest
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
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")

    print(f"\nGenerated {len(SPECS)} musescore3 fixtures.")


if __name__ == "__main__":
    main()
