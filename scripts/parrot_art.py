#!/usr/bin/env python3
"""parrot mascot: scarlet-macaw block art in 24-bit ANSI color.

Standalone renderer, not a hook. Run directly:

    python3 scripts/parrot_art.py

Color drops out under NO_COLOR (https://no-color.org/) or when stdout
is not a terminal, so piping yields plain block art.
"""
import os
import sys

RESET = "\033[0m"

PALETTE: dict[str, tuple[int, int, int]] = {
    "red": (217, 45, 32),  # head, body, tail center
    "white": (244, 239, 229),  # bare face patch
    "ink": (24, 20, 18),  # eye
    "bone": (226, 214, 190),  # beak
    "yellow": (244, 176, 22),  # median wing coverts
    "blue": (0, 118, 190),  # flight feathers, tail tip
    "sky": (94, 170, 226),  # outer feather edges
    "gray": (96, 90, 84),  # legs
    "brown": (121, 85, 48),  # branch
}

# Each line is a list of (palette key, text) runs; runs concatenate to the
# uncolored art exactly, so the plain path needs no separate copy.
LINES: list[list[tuple[str, str]]] = [
    [("red", "                ▄▄▄▄▄▄▄▄▄▄▄▄")],
    [("red", "            ▄▄▄▄████████████▄▄▄▄")],
    [("red", "          ▄▄████████████████████▄▄")],
    [("red", "        ▄▄████████████████████████▄▄")],
    [("red", "      ▄▄████"), ("white", "░░░░░░░░░░"), ("red", "██████████████▄▄")],
    [("bone", "▄▄▄▄▄▄"), ("red", "██████"), ("white", "░░"), ("ink", "████"),
     ("white", "░░░░"), ("red", "████████████████▄▄")],
    [("bone", "██████"), ("red", "██████"), ("white", "░░"), ("ink", "████"),
     ("white", "░░░░"), ("red", "██████████████████▄▄")],
    [("bone", "████▀▀"), ("red", "██████"), ("white", "░░░░░░░░░░"),
     ("red", "████████████████████▄▄")],
    [("bone", "▀▀██  "), ("red", "██████████████████████████████████████▄▄")],
    [("bone", "  ▀▀  "), ("red", "▀▀██████████████████"),
     ("yellow", "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"), ("red", "██")],
    [("red", "        ████████████████"), ("yellow", "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"),
     ("red", "██")],
    [("red", "        ▀▀██████████████"), ("yellow", "▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"),
     ("red", "██")],
    [("red", "          ████████████"), ("yellow", "▓▓▓▓▓▓▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒▒▒"), ("red", "██")],
    [("red", "          ▀▀██████████"), ("yellow", "▓▓▓▓▓▓▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒▒▒"), ("red", "██")],
    [("red", "            ████████"), ("yellow", "▓▓▓▓▓▓▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒"), ("sky", "░░░░"), ("red", "██")],
    [("red", "            ▀▀██████"), ("yellow", "▓▓▓▓▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒"), ("sky", "░░░░░░░░"), ("blue", "▄▄")],
    [("red", "              ████"), ("yellow", "▓▓▓▓▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒"), ("sky", "░░░░░░░░░░"), ("blue", "██")],
    [("red", "              ▀▀██"), ("yellow", "▓▓▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒"), ("sky", "░░░░░░░░░░░░"), ("blue", "▀▀")],
    [("red", "                ██"), ("yellow", "▓▓▓▓"),
     ("blue", "▒▒▒▒▒▒▒▒▒▒"), ("sky", "░░░░░░░░░░░░"), ("blue", "▀▀")],
    [("red", "                ▀▀"), ("gray", "████"), ("blue", "▒▒▒▒▒▒▒▒"),
     ("sky", "░░░░░░░░░░░░"), ("blue", "▀▀")],
    [("gray", "                  ████"), ("red", "  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▀▀")],
    [("gray", "                  ████"), ("red", "    ░░░░░░░░░░░░▀▀")],
    [("brown", "  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄"), ("red", "▒▒▒▒▒▒▒▒"),
     ("brown", "▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄")],
    [("red", "                            ░░░░░░░░")],
    [("red", "                            ▒▒▒▒▒▒")],
    [("blue", "                              ░░░░")],
    [("blue", "                              ▒▒▀▀")],
    [("blue", "                              ▀▀")],
]


def render(color: bool) -> str:
    if not color:
        return "\n".join("".join(text for _, text in line) for line in LINES)
    codes = {key: f"\033[38;2;{r};{g};{b}m" for key, (r, g, b) in PALETTE.items()}
    return "\n".join(
        "".join(f"{codes[key]}{text}" for key, text in line) + RESET
        for line in LINES
    )


def main() -> int:
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    print(render(color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
