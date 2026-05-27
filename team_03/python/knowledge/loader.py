from __future__ import annotations
import json
from pathlib import Path


def load_knowledge(knowledge_dir: Path, category: str, keywords: list[str]) -> str:
    """Load relevant knowledge files based on category and keywords.

    Scans knowledge/{category}/ and knowledge/general/ for JSON files whose
    filenames match any of the provided keywords.  Returns concatenated content
    as a single string suitable for injecting into an LLM prompt.

    Returns an empty string when nothing matches (the LLM then falls back to
    its training knowledge).
    """
    if not knowledge_dir.is_dir():
        return ""

    dirs_to_scan: list[Path] = []
    category_dir = knowledge_dir / category
    general_dir = knowledge_dir / "general"
    if category_dir.is_dir():
        dirs_to_scan.append(category_dir)
    if general_dir.is_dir():
        dirs_to_scan.append(general_dir)

    if not dirs_to_scan:
        return ""

    keywords_lower = [k.lower() for k in keywords]
    matched_chunks: list[str] = []

    for directory in dirs_to_scan:
        for file_path in sorted(directory.glob("*.json")):
            name_lower = file_path.stem.lower()
            if any(kw in name_lower for kw in keywords_lower):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    matched_chunks.append(_format_knowledge(data, file_path.name))
                except (json.JSONDecodeError, OSError):
                    continue

    return "\n\n".join(matched_chunks)


def load_all_knowledge(knowledge_dir: Path, category: str) -> str:
    """Load *all* knowledge files for a category + general."""
    if not knowledge_dir.is_dir():
        return ""

    dirs_to_scan: list[Path] = []
    category_dir = knowledge_dir / category
    general_dir = knowledge_dir / "general"
    if category_dir.is_dir():
        dirs_to_scan.append(category_dir)
    if general_dir.is_dir():
        dirs_to_scan.append(general_dir)

    chunks: list[str] = []
    for directory in dirs_to_scan:
        for file_path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                chunks.append(_format_knowledge(data, file_path.name))
            except (json.JSONDecodeError, OSError):
                continue

    return "\n\n".join(chunks)


def _format_knowledge(data: dict, filename: str) -> str:
    """Turn a knowledge JSON object into a readable text block."""
    source = data.get("source", filename)
    topic = data.get("topic", "")
    header = f"[{source}] {topic}".strip()

    lines = [header, "-" * len(header)]
    for fact in data.get("facts", []):
        rule = fact.get("rule", "")
        value = fact.get("value_m", fact.get("value", ""))
        unit = fact.get("unit", "m" if "value_m" in fact else "")
        context = fact.get("context", "")
        line = f"- {rule}: {value}{unit}"
        if context:
            line += f"  ({context})"
        lines.append(line)

    return "\n".join(lines)
