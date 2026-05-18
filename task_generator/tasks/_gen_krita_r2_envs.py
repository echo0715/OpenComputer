"""Generate env .kra files for krita round 2 tasks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _gen_krita_envs import create_kra, PL

BASE = Path(__file__).parent

TASKS = [
    ("krita_convert_to_grayscale", "colorful.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="Colorful", color_space="RGBA")),
    ("krita_set_resolution_150dpi", "resolution.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="Res", x_res=300, y_res=300)),
    ("krita_set_document_title_metadata", "untitled.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="Untitled")),
    ("krita_set_author_metadata", "noauthor.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="NoAuthor", author="")),
    ("krita_delete_specific_layer", "del.kra",
     dict(width=800, height=600, layers=[PL("KeepA"), PL("DeleteMe"), PL("KeepB")], title="Del")),
    ("krita_merge_down_layer", "merge.kra",
     dict(width=800, height=600, layers=[PL("Base"), PL("Mid"), PL("Top")], title="Merge")),
    ("krita_export_bmp", "bmp_src.kra",
     dict(width=640, height=480, layers=[PL("Background")], title="BMP")),
    ("krita_export_tiff", "tiff_src.kra",
     dict(width=640, height=480, layers=[PL("Background")], title="TIFF")),
    ("krita_duplicate_layer_named", "dupe.kra",
     dict(width=800, height=600, layers=[PL("Base")], title="Dupe")),
    ("krita_resize_hd_1920", "hd.kra",
     dict(width=800, height=600, layers=[PL("Background")], title="HD")),
]


def main():
    for tid, fname, kw in TASKS:
        out = BASE / tid / "env" / fname
        create_kra(str(out), **kw)
        import zipfile
        with zipfile.ZipFile(str(out)) as zf:
            assert "maindoc.xml" in zf.namelist()
        print("OK", out)


if __name__ == "__main__":
    main()
