from __future__ import annotations

from rich.box import ROUNDED
from rich.panel import Panel

from ..version import __version__

PRODUCT_NAME = "HighlighterCS2"
TAGLINE = "CS2 demo highlight recorder"


class Banner:
    @staticmethod
    def build(subtitle: str = TAGLINE) -> Panel:
        return Panel(
            f"[brand]{PRODUCT_NAME}[/brand] [muted]{__version__}[/muted]\n[muted]{subtitle}[/muted]",
            box=ROUNDED,
            border_style="muted",
            padding=(0, 2),
            expand=False,
        )
