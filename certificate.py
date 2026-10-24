"""Генерация именного сертификата (PNG) с помощью Pillow."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
W, H = 1600, 1130

GREEN = (31, 92, 58)
GOLD = (201, 162, 39)
CREAM = (251, 247, 236)
INK = (40, 40, 40)
GRAY = (110, 110, 110)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _centered(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill) -> None:
    w = draw.textlength(text, font=font)
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


def _fit(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int, bold: bool):
    """Подбирает размер шрифта, чтобы текст влез по ширине."""
    size = start
    while size > 28:
        f = _font(size, bold)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 4
    return _font(28, bold)


def make_certificate(name: str, score: int, max_score: int, tier_title: str, ui: dict, date_str: str) -> bytes:
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # рамка
    d.rectangle([30, 30, W - 30, H - 30], outline=GREEN, width=10)
    d.rectangle([56, 56, W - 56, H - 56], outline=GOLD, width=3)

    # уголки
    for cx, cy in [(56, 56), (W - 56, 56), (56, H - 56), (W - 56, H - 56)]:
        d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=GOLD)

    # заголовок
    _centered(d, 130, ui["c_title"], _font(110, True), GREEN)
    d.line([(560, 275), (W - 560, 275)], fill=GOLD, width=4)
    _centered(d, 305, ui["c_sub"], _font(38), GRAY)
    _centered(d, 365, ui["c_quest"], _fit(d, ui["c_quest"], 1300, 64, True), GREEN)

    # имя
    name = name.strip() or "—"
    f_name = _fit(d, name, 1250, 96, True)
    _centered(d, 520, name, f_name, INK)
    d.line([(300, 650), (W - 300, 650)], fill=GRAY, width=2)

    # результат
    _centered(d, 700, ui["c_result"].format(s=score, m=max_score), _font(52, True), INK)
    title = tier_title.split(" ", 1)[1] if " " in tier_title else tier_title  # без эмодзи
    _centered(d, 790, title, _fit(d, title, 1250, 60, True), GOLD)

    # печать с галочкой
    cx, cy, r = 1400, 862, 68
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GREEN)
    d.ellipse([cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10], outline=CREAM, width=4)
    d.line([(cx - 30, cy + 2), (cx - 8, cy + 26), (cx + 34, cy - 26)], fill=CREAM, width=12, joint="curve")

    # низ
    d.text((130, 905), ui["c_date"].format(d=date_str), font=_font(34), fill=GRAY)
    _centered(d, 985, ui["c_motto"], _font(36, True), GREEN)
    _centered(d, 1045, ui["c_note"], _font(24), GRAY)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
