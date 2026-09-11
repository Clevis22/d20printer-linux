"""Image and text rendering for the 384-dot D20 head."""

from __future__ import annotations

from pathlib import Path

from .protocol import PRINT_WIDTH_DOTS, Raster


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as error:
        raise RuntimeError("image printing requires Pillow") from error
    return Image, ImageDraw, ImageFont, ImageOps


def pack_monochrome(image: object) -> Raster:
    Image, _, _, _ = _pillow()
    if image.mode != "1":
        raise ValueError("image must be Pillow mode 1")
    width, height = image.size
    if width % 8:
        raise ValueError("image width must be a multiple of 8")
    pixels = image.load()
    output = bytearray((width // 8) * height)
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0:
                output[y * (width // 8) + x // 8] |= 1 << (7 - (x % 8))
    return Raster(width, height, bytes(output))


def prepare_image(
    path: str | Path,
    *,
    dither: bool = True,
    threshold: int = 128,
    max_height: int = 8192,
) -> Raster:
    Image, _, _, ImageOps = _pillow()
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("L")
    if image.width != PRINT_WIDTH_DOTS:
        height = max(1, round(image.height * PRINT_WIDTH_DOTS / image.width))
        image = image.resize((PRINT_WIDTH_DOTS, height), Image.Resampling.LANCZOS)
    if image.height > max_height:
        raise ValueError(
            f"rendered image is {image.height} rows; safety limit is {max_height}"
        )
    if dither:
        mono = image.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        mono = image.point(lambda value: 255 if value >= threshold else 0, mode="1")
    return pack_monochrome(mono)


def _find_font(ImageFont: object, font: str | Path | None, size: int):
    if font is not None:
        return ImageFont.truetype(str(font), size)
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _wrap_text(draw: object, text: str, font: object, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def render_text(
    text: str,
    *,
    font: str | Path | None = None,
    font_size: int = 28,
    margin: int = 12,
    line_spacing: int = 6,
) -> Raster:
    Image, ImageDraw, ImageFont, _ = _pillow()
    if not 0 <= margin < PRINT_WIDTH_DOTS // 2:
        raise ValueError("invalid text margin")
    font_object = _find_font(ImageFont, font, font_size)
    measuring = ImageDraw.Draw(Image.new("L", (1, 1), 255))
    lines = _wrap_text(measuring, text, font_object, PRINT_WIDTH_DOTS - 2 * margin)
    boxes = [measuring.textbbox((0, 0), line or " ", font=font_object) for line in lines]
    heights = [box[3] - box[1] for box in boxes]
    height = 2 * margin + sum(heights) + line_spacing * max(0, len(lines) - 1)
    image = Image.new("1", (PRINT_WIDTH_DOTS, max(1, height)), 1)
    draw = ImageDraw.Draw(image)
    y = margin
    for line, box, line_height in zip(lines, boxes, heights):
        draw.text((margin, y - box[1]), line, fill=0, font=font_object)
        y += line_height + line_spacing
    return pack_monochrome(image)
