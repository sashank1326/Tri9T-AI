import difflib
from typing import Dict, Any, List


def generate_text_diff(text1: str, text2: str, label1: str = "v1", label2: str = "v2") -> str:
    """Generate unified diff string between two text versions."""
    lines1 = [line + "\n" for line in (text1 or "").splitlines()]
    lines2 = [line + "\n" for line in (text2 or "").splitlines()]
    diff = difflib.unified_diff(lines1, lines2, fromfile=label1, tofile=label2, lineterm="")
    return "".join(diff).strip()


def summarize_text_changes(text1: str, text2: str) -> Dict[str, Any]:
    """
    Summarize additions and deletions between two text snippets.
    Returns counts and sample modified lines.
    """
    s1 = [line.strip() for line in (text1 or "").splitlines() if line.strip()]
    s2 = [line.strip() for line in (text2 or "").splitlines() if line.strip()]

    matcher = difflib.SequenceMatcher(None, s1, s2)
    added = []
    removed = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ('replace', 'delete'):
            removed.extend(s1[i1:i2])
        if tag in ('replace', 'insert'):
            added.extend(s2[j1:j2])

    summary_parts = []
    if added:
        summary_parts.append(f"{len(added)} line(s) added")
    if removed:
        summary_parts.append(f"{len(removed)} line(s) removed")

    return {
        "similarity_ratio": round(matcher.ratio(), 3),
        "added_lines": added,
        "removed_lines": removed,
        "summary": ", ".join(summary_parts) if summary_parts else "No textual differences",
        "unified_diff": generate_text_diff(text1, text2)
    }
