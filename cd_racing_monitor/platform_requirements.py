from __future__ import annotations

from pathlib import Path
import os


DEFAULT_REQUIREMENTS_DIR = Path(r"E:\CD级素材\平台要求")


def platform_requirements_dir() -> Path:
    configured = os.getenv("CD_PLATFORM_REQUIREMENTS_DIR", "").strip()
    return Path(configured) if configured else DEFAULT_REQUIREMENTS_DIR


def read_platform_requirements(path: str | Path | None = None) -> str:
    root = Path(path) if path else platform_requirements_dir()
    if not root.exists():
        return ""

    files = sorted(
        item
        for item in root.rglob("*")
        if item.is_file() and item.suffix.lower() in {".md", ".txt"}
    )
    sections: list[str] = []
    for item in files:
        try:
            content = item.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = item.read_text(encoding="gb18030", errors="replace")
        sections.append(f"# 来源文件：{item}\n\n{content.strip()}")
    return "\n\n---\n\n".join(section for section in sections if section.strip())
