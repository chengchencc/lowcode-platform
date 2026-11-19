"""把 .docx 的正文抽取成 Markdown（仅标准库，无需 python-docx）。

用途：Spec Pack 需要让独立测试设计上下文读到业务章程，但 .docx 不可直接检索。
只抽取正文段落与表格，图片/页眉页脚/批注忽略。

用法：
    python scripts/extract_docx_text.py input.docx output.md
"""

from __future__ import annotations

import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{W}t")).strip()


def heading_level(paragraph: ET.Element) -> int:
    """从 pStyle 猜标题级别。中文 Word 常见 val=1/2/3 或 Heading1/标题 1。"""
    ppr = paragraph.find(f"{W}pPr")
    if ppr is None:
        return 0
    style = ppr.find(f"{W}pStyle")
    if style is None:
        return 0
    value = (style.get(f"{W}val") or "").strip()
    lowered = value.lower()
    if "title" in lowered or "标题" in value:
        return 1
    match = re.search(r"(\d+)$", value)
    if match:
        return min(int(match.group(1)), 6)
    return 0


def cell_text(cell: ET.Element) -> str:
    parts = [paragraph_text(p) for p in cell.findall(f"{W}p")]
    return " ".join(part for part in parts if part).replace("|", r"\|")


def table_markdown(table: ET.Element) -> list[str]:
    rows: list[list[str]] = []
    for row in table.findall(f"{W}tr"):
        cells = [cell_text(cell) for cell in row.findall(f"{W}tc")]
        if cells:
            rows.append(cells)
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def convert(source: str, target: str) -> None:
    with zipfile.ZipFile(source) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{W}body")
    if body is None:
        raise SystemExit("docx 中没有 word/document.xml/body")

    lines: list[str] = []
    for child in body:
        if child.tag == f"{W}p":
            text = paragraph_text(child)
            if not text:
                continue
            level = heading_level(child)
            lines.append(f"{'#' * level} {text}" if level else text)
            lines.append("")
        elif child.tag == f"{W}tbl":
            lines.extend(table_markdown(child))
            lines.append("")

    with open(target, "w", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(lines).rstrip() + "\n")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("用法：python scripts/extract_docx_text.py input.docx output.md")
    convert(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
