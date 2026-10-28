"""Generate docs/demo.gif: a scripted terminal run of the real CLI output.

Frames are rendered with Pillow (no display server needed). The verdict line
is the literal output of:
  swapgate compare --suite examples/sarvam-swap/suite.json \
    --baseline mock:parity --candidate mock:regress --fail-under 0.5
which currently prints `baseline 0.5 candidate 0.0 gap 0.5 -> FAIL`.
Re-run this script if the CLI output format changes.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "demo.gif")

W, H = 720, 244
PAD = 28
BG = (13, 17, 22)
TEXT = (235, 231, 228)
DIM = (159, 164, 171)
PROMPT = (225, 176, 110)
FAIL = (232, 112, 79)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]
SIZE = 19
LINE_H = 30


def _font() -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, SIZE)
    return ImageFont.load_default()


FONT = _font()
PROMPT_W = int(FONT.getlength("$ "))

CMD1 = "pip install swapgate"
OUT1 = "Successfully installed swapgate-0.2.2"
CMD2A = "swapgate compare --suite sarvam.json \\"
CMD2B = "  --baseline mock:parity --candidate mock:regress \\"
CMD2C = "  --fail-under 0.5"
VERDICT = "baseline 0.5 candidate 0.0 gap 0.5 -> FAIL"


def _blank() -> Image.Image:
    return Image.new("RGB", (W, H), BG)


def _text(draw: ImageDraw.ImageDraw, row: int, prompt: bool, body: str,
          color: tuple[int, int, int] = TEXT, cursor: bool = False) -> None:
    y = PAD + row * LINE_H
    x = PAD
    if prompt:
        draw.text((x, y), "$", font=FONT, fill=PROMPT)
        x += PROMPT_W
    draw.text((x, y), body, font=FONT, fill=color)
    if cursor:
        cx = x + int(FONT.getlength(body)) + 3
        draw.rectangle([cx, y + 2, cx + 10, y + SIZE + 2], fill=TEXT)


def build_frames() -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []

    def snap(rows: list, cursor_row: int = -1, ms: int = 70) -> None:
        img = _blank()
        draw = ImageDraw.Draw(img)
        for i, (prompt, body, color) in enumerate(rows):
            _text(draw, i, prompt, body, color, cursor=(i == cursor_row))
        frames.append(img)
        durations.append(ms)

    # Beat 1: type the install command.
    for n in range(0, len(CMD1) + 1, 3):
        snap([(True, CMD1[:n], TEXT)], cursor_row=0)
    snap([(True, CMD1, TEXT)], cursor_row=0, ms=350)
    # Beat 2: install output, then the compare command.
    base = [(True, CMD1, TEXT), (False, OUT1, DIM)]
    snap(base, ms=500)
    for n in range(0, len(CMD2A) + 1, 4):
        snap(base + [(True, CMD2A[:n], TEXT)], cursor_row=2)
    typed = base + [(True, CMD2A, TEXT)]
    for n in range(0, len(CMD2B) + 1, 4):
        snap(typed + [(False, CMD2B[:n], TEXT)], cursor_row=3)
    typed2 = typed + [(False, CMD2B, TEXT)]
    for n in range(0, len(CMD2C) + 1, 4):
        snap(typed2 + [(False, CMD2C[:n], TEXT)], cursor_row=4)
    full = typed2 + [(False, CMD2C, TEXT)]
    snap(full, cursor_row=4, ms=450)
    # Beat 3: the verdict (FAIL in red), then hold.
    snap(full + [(False, VERDICT, TEXT)], ms=300)
    img = _blank()
    draw = ImageDraw.Draw(img)
    for i, (prompt, body, color) in enumerate(full):
        _text(draw, i, prompt, body, color)
    head, _, _tail = VERDICT.rpartition("FAIL")
    _text(draw, 5, False, head, TEXT)
    vx = PAD + int(FONT.getlength(head))
    draw.text((vx, PAD + 5 * LINE_H), "FAIL", font=FONT, fill=FAIL)
    frames.append(img)
    durations.append(2600)
    return frames, durations


def main() -> None:
    frames, durations = build_frames()
    frames[0].save(
        OUT, save_all=True, append_images=frames[1:], duration=durations,
        loop=0, optimize=True,
    )
    print(f"wrote {OUT}: {len(frames)} frames, "
          f"{os.path.getsize(OUT) // 1024} KiB")


if __name__ == "__main__":
    main()
