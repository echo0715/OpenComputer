"""Generate env files for zotero gap tasks.

Creates per-task env/ directories with zotero.sqlite copies (modified where needed)
and PDF / RIS / BibTeX / CSV companion files.
"""
import os
import shutil
import sqlite3
import json
from pathlib import Path

BASE = Path(__file__).parent
SRC_SQLITE = BASE / "zotero_add_author_to_survey" / "env" / "zotero.sqlite"


def make_pdf(path: Path, title: str, body_lines):
    """Write a minimal valid PDF 1.4 with Helvetica, one page."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Build content stream
    content_lines = ["BT", "/F1 14 Tf", "72 760 Td", f"({_pdf_escape(title)}) Tj"]
    y = 720
    for line in body_lines:
        content_lines.append("0 -18 Td")
        content_lines.append(f"({_pdf_escape(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")
    stream_obj = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"

    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        stream_obj,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref_off = len(out)
    out.extend(f"xref\n0 {len(objs)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref_off}\n%%EOF\n".encode())
    path.write_bytes(bytes(out))


def _pdf_escape(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def copy_sqlite(dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_SQLITE, dst_dir / "zotero.sqlite")


def write_manifest(task_dir: Path, task_id: str, files):
    (task_dir / "env_manifest.json").write_text(
        json.dumps({"task_id": task_id, "files": files}, indent=2) + "\n"
    )


def seed_duplicate(dst_dir: Path):
    """Insert a second 'Attention Is All You Need' item without a DOI for merge task."""
    copy_sqlite(dst_dir)
    path = dst_dir / "zotero.sqlite"
    conn = sqlite3.connect(path)
    c = conn.cursor()
    # Find typeID for journalArticle
    c.execute("SELECT itemTypeID FROM itemTypes WHERE typeName='journalArticle'")
    type_id = c.fetchone()[0]
    # Create new item
    import uuid
    key = "DUPLICATE0"
    c.execute(
        "INSERT INTO items (itemTypeID, dateAdded, dateModified, clientDateModified, libraryID, key, version, synced) "
        "VALUES (?, datetime('now'), datetime('now'), datetime('now'), 1, ?, 0, 0)",
        (type_id, key),
    )
    new_item_id = c.lastrowid
    # Find title fieldID and add value
    c.execute("SELECT fieldID FROM fields WHERE fieldName='title'")
    title_fid = c.fetchone()[0]
    title_val = "Attention Is All You Need"
    c.execute("SELECT valueID FROM itemDataValues WHERE value=?", (title_val,))
    row = c.fetchone()
    if row:
        title_vid = row[0]
    else:
        c.execute("INSERT INTO itemDataValues (value) VALUES (?)", (title_val,))
        title_vid = c.lastrowid
    c.execute(
        "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
        (new_item_id, title_fid, title_vid),
    )
    # Ensure the ORIGINAL item has DOI = 10.48550/arXiv.1706.03762
    c.execute("SELECT fieldID FROM fields WHERE fieldName='DOI'")
    doi_fid = c.fetchone()[0]
    # Find original attention item (the one that existed before our insert)
    c.execute(
        "SELECT i.itemID FROM items i JOIN itemData id ON id.itemID=i.itemID "
        "JOIN itemDataValues v ON v.valueID=id.valueID JOIN fields f ON id.fieldID=f.fieldID "
        "WHERE f.fieldName='title' AND v.value=? AND i.itemID != ?",
        (title_val, new_item_id),
    )
    orig_id = c.fetchone()[0]
    doi_val = "10.48550/arXiv.1706.03762"
    c.execute("SELECT valueID FROM itemDataValues WHERE value=?", (doi_val,))
    row = c.fetchone()
    if row:
        doi_vid = row[0]
    else:
        c.execute("INSERT INTO itemDataValues (value) VALUES (?)", (doi_val,))
        doi_vid = c.lastrowid
    c.execute(
        "SELECT 1 FROM itemData WHERE itemID=? AND fieldID=?", (orig_id, doi_fid)
    )
    if not c.fetchone():
        c.execute(
            "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
            (orig_id, doi_fid, doi_vid),
        )
    conn.commit()
    conn.close()


# ------------ Task env builders ------------

TASKS = []

def task_attach_pdf():
    tid = "zotero_gap_attach_pdf_to_item"
    d = BASE / tid / "env"
    copy_sqlite(d)
    make_pdf(
        d / "attention_paper.pdf",
        "Attention Is All You Need",
        ["Vaswani et al., 2017", "A placeholder PDF for the transformer paper.",
         "Section 1: Introduction", "We propose the Transformer."],
    )
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "attention_paper.pdf", "sandbox_path": "/home/user/Documents/attention_paper.pdf", "type": "pdf"},
        ],
    )


def task_pdf_note():
    tid = "zotero_gap_add_pdf_annotation_note"
    d = BASE / tid / "env"
    copy_sqlite(d)
    make_pdf(
        d / "deep_learning.pdf",
        "Deep Learning",
        ["Goodfellow, Bengio, Courville", "Chapter 1: Introduction",
         "Key definitions: neural network, layer, activation.", "Placeholder content."],
    )
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "deep_learning.pdf", "sandbox_path": "/home/user/Documents/deep_learning.pdf", "type": "pdf"},
        ],
    )


def task_advanced_search_export():
    tid = "zotero_gap_advanced_search_export_results"
    d = BASE / tid / "env"
    copy_sqlite(d)
    write_manifest(
        BASE / tid, tid,
        [{"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"}],
    )


def task_import_ris():
    tid = "zotero_gap_import_ris_file"
    d = BASE / tid / "env"
    copy_sqlite(d)
    ris = """TY  - JOUR
TI  - GPT-4 Technical Report
AU  - OpenAI
PY  - 2023
JO  - arXiv preprint
DO  - 10.48550/arXiv.2303.08774
ER  -
"""
    (d / "new_papers.ris").write_text(ris)
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "new_papers.ris", "sandbox_path": "/home/user/Documents/new_papers.ris", "type": "ris"},
        ],
    )


def task_import_bibtex():
    tid = "zotero_gap_import_bibtex_file"
    d = BASE / tid / "env"
    copy_sqlite(d)
    bib = """@article{touvron2023llama,
  title = {LLaMA: Open and Efficient Foundation Language Models},
  author = {Touvron, Hugo and Lavril, Thibaut and Izacard, Gautier},
  year = {2023},
  journal = {arXiv preprint arXiv:2302.13971}
}

@article{chowdhery2022palm,
  title = {PaLM: Scaling Language Modeling with Pathways},
  author = {Chowdhery, Aakanksha and Narang, Sharan},
  year = {2022},
  journal = {arXiv preprint arXiv:2204.02311}
}
"""
    (d / "citations.bib").write_text(bib)
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "citations.bib", "sandbox_path": "/home/user/Documents/citations.bib", "type": "bibtex"},
        ],
    )


def task_duplicate_merge():
    tid = "zotero_gap_duplicate_merge"
    d = BASE / tid / "env"
    seed_duplicate(d)
    write_manifest(
        BASE / tid, tid,
        [{"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"}],
    )


def task_csv_import():
    tid = "zotero_gap_csv_import_via_ris_conversion"
    d = BASE / tid / "env"
    copy_sqlite(d)
    csv_text = """Title,Author,Year,Journal,DOI
Efficient Estimation of Word Representations,Mikolov,2013,arXiv,10.48550/arXiv.1301.3781
GloVe: Global Vectors for Word Representation,Pennington,2014,EMNLP,10.3115/v1/D14-1162
FastText: Enriching Word Vectors with Subword Information,Bojanowski,2017,TACL,10.1162/tacl_a_00051
"""
    (d / "bibliography.csv").write_text(csv_text)
    ris = """TY  - JOUR
TI  - Efficient Estimation of Word Representations
AU  - Mikolov, Tomas
PY  - 2013
JO  - arXiv
DO  - 10.48550/arXiv.1301.3781
ER  -

TY  - JOUR
TI  - GloVe: Global Vectors for Word Representation
AU  - Pennington, Jeffrey
PY  - 2014
JO  - EMNLP
DO  - 10.3115/v1/D14-1162
ER  -

TY  - JOUR
TI  - FastText: Enriching Word Vectors with Subword Information
AU  - Bojanowski, Piotr
PY  - 2017
JO  - TACL
DO  - 10.1162/tacl_a_00051
ER  -
"""
    (d / "bibliography.ris").write_text(ris)
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "bibliography.csv", "sandbox_path": "/home/user/Documents/bibliography.csv", "type": "csv"},
            {"filename": "bibliography.ris", "sandbox_path": "/home/user/Documents/bibliography.ris", "type": "ris"},
        ],
    )


def task_pdf_and_tag():
    tid = "zotero_gap_pdf_and_color_tag"
    d = BASE / tid / "env"
    copy_sqlite(d)
    make_pdf(
        d / "bert_paper.pdf",
        "BERT: Pre-training of Deep Bidirectional Transformers",
        ["Devlin et al., 2019", "Abstract: We introduce BERT.",
         "Section 1: Introduction", "Placeholder content."],
    )
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "bert_paper.pdf", "sandbox_path": "/home/user/Documents/bert_paper.pdf", "type": "pdf"},
        ],
    )


def task_multi_pdf_attach():
    tid = "zotero_gap_multi_pdf_attach"
    d = BASE / tid / "env"
    copy_sqlite(d)
    make_pdf(d / "attention.pdf", "Attention Is All You Need", ["Vaswani et al. 2017", "Transformer paper."])
    make_pdf(d / "bert.pdf", "BERT Paper", ["Devlin et al. 2019", "BERT bidirectional transformer."])
    make_pdf(d / "deep_learning.pdf", "Deep Learning", ["Goodfellow et al. 2016", "Book."])
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "attention.pdf", "sandbox_path": "/home/user/Documents/attention.pdf", "type": "pdf"},
            {"filename": "bert.pdf", "sandbox_path": "/home/user/Documents/bert.pdf", "type": "pdf"},
            {"filename": "deep_learning.pdf", "sandbox_path": "/home/user/Documents/deep_learning.pdf", "type": "pdf"},
        ],
    )


def task_ris_into_collection():
    tid = "zotero_gap_ris_into_new_collection"
    d = BASE / tid / "env"
    copy_sqlite(d)
    ris = """TY  - JOUR
TI  - ELECTRA: Pre-training Text Encoders as Discriminators
AU  - Clark, Kevin
PY  - 2020
JO  - ICLR
ER  -

TY  - JOUR
TI  - RoBERTa: A Robustly Optimized BERT Pretraining Approach
AU  - Liu, Yinhan
PY  - 2019
JO  - arXiv
ER  -
"""
    (d / "nlp_papers.ris").write_text(ris)
    write_manifest(
        BASE / tid, tid,
        [
            {"filename": "zotero.sqlite", "sandbox_path": "/home/user/Zotero/zotero.sqlite", "type": "sqlite"},
            {"filename": "nlp_papers.ris", "sandbox_path": "/home/user/Documents/nlp_papers.ris", "type": "ris"},
        ],
    )


def main():
    task_attach_pdf()
    task_pdf_note()
    task_advanced_search_export()
    task_import_ris()
    task_import_bibtex()
    task_duplicate_merge()
    task_csv_import()
    task_pdf_and_tag()
    task_multi_pdf_attach()
    task_ris_into_collection()
    print("All env files generated.")


if __name__ == "__main__":
    main()
