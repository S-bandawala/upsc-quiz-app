"""Try to extract text from answer key PDFs (page 1 = Set A only)."""
import fitz
import re
from pathlib import Path

PAPERS_DIR = Path(__file__).resolve().parent.parent.parent / "UPSC_CSP_Papers"
YEARS = [2015, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

for year in YEARS:
    ak = PAPERS_DIR / str(year) / "Answer_Keys" / f"UPSC_CSP_{year}_AnswerKey_GS-Paper-I.pdf"
    if not ak.exists():
        print(f"[{year}] Not found")
        continue
    doc = fitz.open(str(ak))
    text = doc[0].get_text()
    # Check if there's useful text
    nums = re.findall(r'\d+', text)
    letters = re.findall(r'[ABCDabcd]', text)
    print(f"[{year}] Text chars: {len(text)}, numbers found: {len(nums)}, A-D letters: {len(letters)}")
    if len(text) > 100:
        print(f"  First 500 chars: {text[:500]}")
    print()
