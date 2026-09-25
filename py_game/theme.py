from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    background: tuple[int, int, int] = (13, 18, 25)
    panel: tuple[int, int, int] = (24, 31, 41)
    panel_alt: tuple[int, int, int] = (32, 42, 54)
    hover: tuple[int, int, int] = (45, 59, 74)
    selected: tuple[int, int, int] = (67, 84, 105)
    border: tuple[int, int, int] = (89, 109, 132)
    text: tuple[int, int, int] = (239, 243, 247)
    muted: tuple[int, int, int] = (156, 169, 184)
    accent: tuple[int, int, int] = (236, 177, 75)
    success: tuple[int, int, int] = (91, 198, 132)
    danger: tuple[int, int, int] = (226, 100, 103)
    disabled: tuple[int, int, int] = (41, 46, 53)
    board_slot: tuple[int, int, int] = (38, 50, 60)


PALETTE = Palette()
