from __future__ import annotations

import sys

from rich.console import Console
from rich.theme import Theme

HIGHLIGHTER_THEME = Theme(
    {
        "brand": "bold cyan",
        "muted": "grey58",
        "accent": "bold magenta",
        "success": "bold green",
        "warning": "yellow",
        "danger": "bold red",
        "side.t": "bold yellow",
        "side.ct": "bold blue",
        "score.high": "bold green",
        "score.mid": "bold yellow",
        "score.low": "grey70",
    }
)

HIGH_SCORE_THRESHOLD = 25.0
MID_SCORE_THRESHOLD = 14.0


def build_console() -> Console:
    enable_utf8_output()
    return Console(theme=HIGHLIGHTER_THEME, highlight=False)


def enable_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def supports_text(console: Console, text: str) -> bool:
    encoding = getattr(console.file, "encoding", None)
    if not encoding:
        return True
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def score_style(score: float) -> str:
    if score >= HIGH_SCORE_THRESHOLD:
        return "score.high"
    if score >= MID_SCORE_THRESHOLD:
        return "score.mid"
    return "score.low"
