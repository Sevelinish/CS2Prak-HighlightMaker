from __future__ import annotations

from dataclasses import dataclass

from ..config.schema import CrosshairConfig

FILL = "t=fill"


@dataclass(frozen=True, slots=True)
class Arm:
    x: str
    y: str
    width: str
    height: str

    def grown(self, amount: int) -> "Arm":
        if amount <= 0:
            return self
        return Arm(
            x=f"({self.x})-{amount}",
            y=f"({self.y})-{amount}",
            width=f"({self.width})+{2 * amount}",
            height=f"({self.height})+{2 * amount}",
        )

    def to_filter(self, color: str, opacity: float) -> str:
        return (
            f"drawbox=x={self.x}:y={self.y}:w={self.width}:h={self.height}"
            f":color={color}@{opacity:g}:{FILL}"
        )


class CrosshairFilterBuilder:
    def __init__(self, style: CrosshairConfig) -> None:
        self._style = style

    def build(self) -> str:
        if not self._style.enabled:
            return ""

        arms = self._arms()
        filters = [
            arm.grown(self._style.outline).to_filter(self._style.outline_color, 1.0)
            for arm in arms
            if self._style.outline > 0
        ]
        filters.extend(arm.to_filter(self._style.color, self._style.opacity) for arm in arms)
        return ",".join(filters)

    def _arms(self) -> list[Arm]:
        length = self._style.length
        gap = self._style.gap
        thickness = self._style.thickness

        horizontal_y = f"(ih-{thickness})/2"
        vertical_x = f"(iw-{thickness})/2"

        arms = [
            Arm(f"iw/2-{gap + length}", horizontal_y, str(length), str(thickness)),
            Arm(f"iw/2+{gap}", horizontal_y, str(length), str(thickness)),
            Arm(vertical_x, f"ih/2-{gap + length}", str(thickness), str(length)),
            Arm(vertical_x, f"ih/2+{gap}", str(thickness), str(length)),
        ]

        if self._style.dot:
            arms.append(Arm(vertical_x, horizontal_y, str(thickness), str(thickness)))

        return arms
