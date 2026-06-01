from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarkdownReport:
    path: str
    raw_text: str
    section_titles: list[str]


def read_markdown_report(path: Path) -> MarkdownReport:
    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    section_titles = [
        line.lstrip("#").strip()
        for line in raw_text.splitlines()
        if line.startswith("#") and line.lstrip("#").strip()
    ]
    return MarkdownReport(str(path), raw_text, section_titles)
