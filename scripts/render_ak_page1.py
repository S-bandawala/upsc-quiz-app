"""Render page 1 (Set A) of each answer key PDF as PNG for visual inspection."""
import fitz
from pathlib import Path

PAPERS_DIR = Path(__file__).resolve().parent.parent.parent / "UPSC_CSP_Papers"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "ak_images"
OUT_DIR.mkdir(exist_ok=True)

YEARS = [2015, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

for year in YEARS:
    ak = PAPERS_DIR / str(year) / "Answer_Keys" / f"UPSC_CSP_{year}_AnswerKey_GS-Paper-I.pdf"
    if not ak.exists():
        print(f"[{year}] Not found")
        continue
    doc = fitz.open(str(ak))
    pix = doc[0].get_pixmap(dpi=200)
    out = OUT_DIR / f"ak_{year}_setA.png"
    pix.save(str(out))
    print(f"[{year}] Saved {out.name} ({doc.page_count} pages total)")
