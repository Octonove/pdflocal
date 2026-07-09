"""Genera build/icon.ico para PDFLocal (hoja con esquina doblada sobre navy)."""

from pathlib import Path
from PIL import Image, ImageDraw

NAVY = (30, 58, 95, 255)
NAVY2 = (21, 48, 77, 255)
TERRA = (206, 110, 97, 255)
WHITE = (255, 255, 255, 255)
PAPER = (250, 252, 255, 255)


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=NAVY)
    d.rounded_rectangle([0, int(size * 0.5), size - 1, size - 1], radius=r, fill=NAVY2)
    # hoja
    m = size * 0.24
    fold = size * 0.20
    x0, y0, x1, y1 = m, m * 0.9, size - m, size - m
    d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)], fill=PAPER)
    d.polygon([(x1 - fold, y0), (x1, y0 + fold), (x1 - fold, y0 + fold)], fill=(210, 220, 232, 255))
    # banda terracota tipo "PDF"
    bh = size * 0.12
    by = y1 - bh - size * 0.06
    d.rounded_rectangle([x0 + size * 0.06, by, x1 - size * 0.10, by + bh], radius=int(size * 0.02),
                        fill=TERRA)
    return img


def main() -> None:
    out = Path(__file__).resolve().parent / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make(s) for s in sizes]
    imgs[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    make(256).save(out.with_name("icon_preview.png"))
    print("icono ->", out)


if __name__ == "__main__":
    main()
