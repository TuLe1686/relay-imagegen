#!/usr/bin/env python3
"""Extract plain text from a .docx using only the stdlib (zip + XML).

No python-docx, no Word COM, no network. Prefer this when an agent needs a
Word script as text before writing prompts/shot-*.txt.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _paragraph_text(p_el: ET.Element) -> str:
    parts: list[str] = []
    for node in p_el.iter():
        if _local(node.tag) == "t" and node.text:
            parts.append(node.text)
        elif _local(node.tag) == "tab":
            parts.append("\t")
        elif _local(node.tag) == "br":
            parts.append("\n")
    return "".join(parts).strip()


def _table_lines(tbl_el: ET.Element) -> list[str]:
    lines: list[str] = []
    for row in tbl_el.findall("w:tr", NS):
        cells: list[str] = []
        for cell in row.findall("w:tc", NS):
            cell_parts = [_paragraph_text(p) for p in cell.findall("w:p", NS)]
            cells.append(" ".join(part for part in cell_parts if part))
        line = " | ".join(cells).strip()
        if line:
            lines.append(line)
    return lines


def extract_docx_text(docx_path: Path) -> str:
    if not docx_path.exists():
        die(f"File not found: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        die(f"Expected a .docx file, got: {docx_path.name}")

    try:
        with zipfile.ZipFile(docx_path) as zf:
            try:
                raw = zf.read("word/document.xml")
            except KeyError:
                die("Not a valid .docx: missing word/document.xml")
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
            text = _paragraph_text(child)
            if text:
                lines.append(text)
        elif name == "tbl":
            lines.extend(_table_lines(child))
        # sectPr and other body children are ignored

    return "\n".join(lines).strip() + ("\n" if lines else "")


def _minimal_docx_bytes(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    """Build a tiny valid-enough docx for --test (document.xml only)."""

    def p_xml(text: str) -> str:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'

    body_parts = [p_xml(p) for p in paragraphs]
    if table:
        rows = []
        for row in table:
            cells = "".join(
                f"<w:tc>{p_xml(cell)}</w:tc>" for cell in row
            )
            rows.append(f"<w:tr>{cells}</w:tr>")
        body_parts.append(f"<w:tbl>{''.join(rows)}</w:tbl>")

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}">'
        f'<w:body>{"".join(body_parts)}<w:sectPr/></w:body>'
        "</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", document.encode("utf-8"))
        zf.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
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
        table=[["镜号", "画面"], ["02", "果园采摘"]],
    )
    tmp = Path(__file__).resolve().parent / "_extract_docx_selftest.docx"
    try:
        tmp.write_bytes(sample)
        text = extract_docx_text(tmp)
    finally:
        if tmp.exists():
            tmp.unlink()

    required = ["镜头1：湖面日出", "旁白：美林湖荔枝季", "镜号 | 画面", "02 | 果园采摘"]
    missing = [item for item in required if item not in text]
    if missing:
        print("SELF_TEST=fail", file=sys.stderr)
        print(f"MISSING={missing!r}", file=sys.stderr)
        print(text, file=sys.stderr)
        return 1
    print("SELF_TEST=ok")
    print(f"CHARS={len(text)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract plain text from .docx with stdlib only (zip + XML)."
    )
    parser.add_argument("docx", nargs="?", help="Path to .docx file")
    parser.add_argument(
        "--out",
        "-o",
        help="Write UTF-8 text here. Default: print to stdout.",
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
    text = extract_docx_text(path)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())