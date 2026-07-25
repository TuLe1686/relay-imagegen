#!/usr/bin/env python3
"""Extract plain text (and optional images) from a .docx using only the stdlib.

No python-docx, no Word COM, no network. Prefer this when an agent needs a
Word script as text before writing prompts/shot-*.txt.

Tables: cells joined with \" | \".
Embedded images: written as [IMAGE:filename] placeholders; use --media-dir to
export the actual files from word/media/.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W_NS, "r": R_NS, "a": A_NS, "pr": REL_NS}

IMAGE_REL_TYPE_SUFFIX = "/image"


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _load_image_rels(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map rId -> media filename (e.g. rId5 -> image1.png)."""
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    mapping: dict[str, str] = {}
    for rel in root:
        if _local(rel.tag) != "Relationship":
            continue
        rel_type = rel.attrib.get("Type", "")
        if not rel_type.endswith(IMAGE_REL_TYPE_SUFFIX) and "/image" not in rel_type:
            # still allow media targets even if type string varies
            target = rel.attrib.get("Target", "")
            if "media/" not in target.replace("\\", "/"):
                continue
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target", "").replace("\\", "/")
        if not rid or not target:
            continue
        name = Path(target).name
        if name:
            mapping[rid] = name
    return mapping


def _embed_ids_in(el: ET.Element) -> list[str]:
    """Collect r:embed / r:id values used by drawings inside an element."""
    ids: list[str] = []
    for node in el.iter():
        # a:blip r:embed="rIdN"
        embed = node.attrib.get(f"{{{R_NS}}}embed") or node.attrib.get("embed")
        if embed:
            ids.append(embed)
            continue
        # v:imagedata r:id=...
        rid = node.attrib.get(f"{{{R_NS}}}id") or node.attrib.get("id")
        if rid and _local(node.tag) in {"imagedata", "blip"}:
            ids.append(rid)
    return ids


def _paragraph_parts(p_el: ET.Element, image_rels: dict[str, str]) -> list[str]:
    parts: list[str] = []
    # Walk in document order: text nodes and image placeholders.
    for node in p_el.iter():
        local = _local(node.tag)
        if local == "t" and node.text:
            parts.append(node.text)
        elif local == "tab":
            parts.append("\t")
        elif local == "br":
            parts.append("\n")
        elif local == "blip":
            embed = node.attrib.get(f"{{{R_NS}}}embed") or node.attrib.get("embed")
            if embed:
                name = image_rels.get(embed, embed)
                parts.append(f"[IMAGE:{name}]")
        elif local == "imagedata":
            rid = node.attrib.get(f"{{{R_NS}}}id") or node.attrib.get("id")
            if rid:
                name = image_rels.get(rid, rid)
                parts.append(f"[IMAGE:{name}]")
    return parts


def _paragraph_text(p_el: ET.Element, image_rels: dict[str, str]) -> str:
    return "".join(_paragraph_parts(p_el, image_rels)).strip()


def _cell_text(cell_el: ET.Element, image_rels: dict[str, str]) -> str:
    """Text + image placeholders from a table cell (including nested tables)."""
    chunks: list[str] = []
    for child in list(cell_el):
        name = _local(child.tag)
        if name == "p":
            text = _paragraph_text(child, image_rels)
            if text:
                chunks.append(text)
        elif name == "tbl":
            chunks.extend(_table_lines(child, image_rels))
    # Fallback: images not inside a paragraph text stream still get markers.
    if not chunks:
        for rid in _embed_ids_in(cell_el):
            name = image_rels.get(rid, rid)
            chunks.append(f"[IMAGE:{name}]")
    return " ".join(chunks).strip()


def _table_lines(tbl_el: ET.Element, image_rels: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for row in tbl_el.findall("w:tr", NS):
        cells = [_cell_text(cell, image_rels) for cell in row.findall("w:tc", NS)]
        # Keep rows that have any non-empty cell (including image-only cells).
        if any(cells):
            lines.append(" | ".join(cells))
    return lines


def extract_docx(
    docx_path: Path,
    media_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """Return (text, exported_media_paths)."""
    if not docx_path.exists():
        die(f"File not found: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        die(f"Expected a .docx file, got: {docx_path.name}")

    exported: list[str] = []
    try:
        with zipfile.ZipFile(docx_path) as zf:
            try:
                raw = zf.read("word/document.xml")
            except KeyError:
                die("Not a valid .docx: missing word/document.xml")
            image_rels = _load_image_rels(zf)

            if media_dir is not None:
                media_dir.mkdir(parents=True, exist_ok=True)
                for name in zf.namelist():
                    norm = name.replace("\\", "/")
                    if not norm.startswith("word/media/") or norm.endswith("/"):
                        continue
                    data = zf.read(name)
                    if not data:
                        continue
                    dest = media_dir / Path(norm).name
                    dest.write_bytes(data)
                    exported.append(str(dest.resolve()))
    except zipfile.BadZipFile:
        die(f"Not a valid .docx zip: {docx_path}")

    root = ET.fromstring(raw)
    body = root.find("w:body", NS)
    if body is None:
        die("Not a valid .docx: missing w:body")

    lines: list[str] = []
    for child in list(body):
        name = _local(child.tag)
        if name == "p":
            text = _paragraph_text(child, image_rels)
            if text:
                lines.append(text)
        elif name == "tbl":
            lines.extend(_table_lines(child, image_rels))

    text = "\n".join(lines).strip() + ("\n" if lines else "")
    return text, exported


def extract_docx_text(docx_path: Path) -> str:
    """Backward-compatible text-only helper."""
    text, _ = extract_docx(docx_path, media_dir=None)
    return text


def _minimal_docx_bytes(
    paragraphs: list[str],
    table: list[list[str]] | None = None,
    with_image: bool = False,
) -> bytes:
    """Build a tiny valid-enough docx for --test."""

    def p_xml(text: str) -> str:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'

    def image_p_xml() -> str:
        return (
            "<w:p><w:r><w:drawing><wp:inline "
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            f'<a:graphic xmlns:a="{A_NS}"><a:graphicData>'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:blipFill><a:blip r:embed="rIdImage" xmlns:r="{R_NS}"/></pic:blipFill>'
            "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        )

    body_parts = [p_xml(p) for p in paragraphs]
    if table:
        rows = []
        for row in table:
            cells_xml = []
            for cell in row:
                if cell == "__IMAGE__":
                    cells_xml.append(f"<w:tc>{image_p_xml()}</w:tc>")
                else:
                    cells_xml.append(f"<w:tc>{p_xml(cell)}</w:tc>")
            rows.append(f"<w:tr>{''.join(cells_xml)}</w:tr>")
        body_parts.append(f"<w:tbl>{''.join(rows)}</w:tbl>")
    elif with_image:
        body_parts.append(image_p_xml())

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f'<w:body>{"".join(body_parts)}<w:sectPr/></w:body>'
        "</w:document>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{REL_NS}">'
        '<Relationship Id="rIdImage" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/>'
        "</Relationships>"
    )
    # 1x1 PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", document.encode("utf-8"))
        zf.writestr("word/_rels/document.xml.rels", rels.encode("utf-8"))
        zf.writestr("word/media/image1.png", png)
        zf.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="png" ContentType="image/png"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )
    return buf.getvalue()


def run_self_test() -> int:
    sample = _minimal_docx_bytes(
        paragraphs=["镜头1：湖面日出", "旁白：美林湖荔枝季"],
        table=[["镜号", "画面"], ["02", "果园采摘"], ["__IMAGE__", "参考图列"]],
        with_image=False,
    )
    tmp = Path(__file__).resolve().parent / "_extract_docx_selftest.docx"
    media = Path(__file__).resolve().parent / "_extract_docx_selftest_media"
    try:
        tmp.write_bytes(sample)
        text, exported = extract_docx(tmp, media_dir=media)
    finally:
        if tmp.exists():
            tmp.unlink()

    required = [
        "镜头1：湖面日出",
        "旁白：美林湖荔枝季",
        "镜号 | 画面",
        "02 | 果园采摘",
        "[IMAGE:image1.png]",
        "参考图列",
    ]
    missing = [item for item in required if item not in text]
    media_ok = any(Path(p).name == "image1.png" for p in exported)
    if missing or not media_ok:
        print("SELF_TEST=fail", file=sys.stderr)
        print(f"MISSING={missing!r}", file=sys.stderr)
        print(f"EXPORTED={exported!r}", file=sys.stderr)
        print(text, file=sys.stderr)
        return 1
    # cleanup media dir
    for p in media.glob("*"):
        p.unlink()
    if media.exists():
        media.rmdir()
    print("SELF_TEST=ok")
    print(f"CHARS={len(text)}")
    print(f"IMAGES=1")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract plain text from .docx with stdlib only (zip + XML). "
            "Tables become ' | ' rows; embedded images become [IMAGE:name] "
            "and can be exported with --media-dir."
        )
    )
    parser.add_argument("docx", nargs="?", help="Path to .docx file")
    parser.add_argument(
        "--out",
        "-o",
        help="Write UTF-8 text here. Default: print to stdout.",
    )
    parser.add_argument(
        "--media-dir",
        help="Export word/media/* images into this directory.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in self-test (no input file required).",
    )
    args = parser.parse_args()

    if args.test:
        return run_self_test()
    if not args.docx:
        parser.error("docx path is required unless --test is set")

    path = Path(args.docx)
    media_dir = Path(args.media_dir) if args.media_dir else None
    text, exported = extract_docx(path, media_dir=media_dir)
    image_markers = re.findall(r"\[IMAGE:([^\]]+)\]", text)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        nonempty = [ln for ln in text.splitlines() if ln.strip()]
        print(f"OUT={out.resolve()}")
        print(f"CHARS={len(text)}")
        print(f"NONEMPTY_LINES={len(nonempty)}")
    else:
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            sys.stdout.write("\n")

    print(f"IMAGE_MARKERS={len(image_markers)}", file=sys.stderr if not args.out else sys.stdout)
    if image_markers:
        print(f"IMAGE_NAMES={','.join(dict.fromkeys(image_markers))}", file=sys.stderr if not args.out else sys.stdout)
    if exported:
        print(f"MEDIA_DIR={media_dir.resolve()}")
        print(f"MEDIA_FILES={len(exported)}")
    elif media_dir is None and image_markers:
        print(
            "NOTE=Document has embedded images. Re-run with --media-dir prompts/_script_media "
            "to export files for agent vision / edit refs.",
            file=sys.stderr if not args.out else sys.stdout,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())