"""
Fix Answer Keys — Extract Set A Only (Page 1)
The original extraction processed ALL pages (Sets A,B,C,D),
so Set D answers overwrote Set A. This script re-extracts from page 1 only.
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import fitz
from groq import Groq

# ── Load .env ──
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

BASE_DIR = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE_DIR.parent / "UPSC_CSP_Papers"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"

ANSWER_KEY_PROMPT = """This is page 1 of an official UPSC answer key — it shows Series/Set A answers.
Extract all question numbers and their correct answers from this page.
The table has columns: Q.No., Key repeated across the row.
Return ONLY valid JSON: {"1": "b", "2": "a", ...}
Use lowercase a/b/c/d only. If a question was dropped/deleted, skip it.
Return answers for ALL 100 questions visible on this page.
"""

YEARS_WITH_AK = [2015, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]


def pdf_page_to_b64(page) -> str:
    pix = page.get_pixmap(dpi=200)  # higher DPI for better accuracy
    return base64.standard_b64encode(pix.tobytes("png")).decode()


def groq_vision(b64_image: str, prompt: str) -> str:
    max_retries = 20
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                        {"type": "text", "text": prompt}
                    ]
                }],
                max_tokens=4000,
                temperature=0.1
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                wait = 60
                m = re.search(r'try again in (\d+)m([\d.]+)s', err_str)
                if m:
                    wait = int(m.group(1)) * 60 + float(m.group(2)) + 5
                else:
                    m2 = re.search(r'try again in ([\d.]+)s', err_str)
                    if m2:
                        wait = float(m2.group(1)) + 5
                print(f"    Rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise Exception("Rate limit exceeded after max retries")


def main():
    print("=" * 60)
    print("Fix Answer Keys — Set A Only (Page 1)")
    print("=" * 60)

    for year in YEARS_WITH_AK:
        ak_path = PAPERS_DIR / str(year) / "Answer_Keys" / f"UPSC_CSP_{year}_AnswerKey_GS-Paper-I.pdf"
        if not ak_path.exists():
            print(f"\n[{year}] Answer key not found — skipping")
            continue

        print(f"\n[{year}] Extracting Set A answers (page 1 only)...")
        doc = fitz.open(str(ak_path))

        if doc.page_count < 1:
            print(f"  Empty PDF — skipping")
            continue

        # Render page 1 at high DPI
        b64 = pdf_page_to_b64(doc[0])

        try:
            raw = groq_vision(b64, ANSWER_KEY_PROMPT)
            m = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
            if m:
                raw_dict = json.loads(m.group())
                answers = {}
                for k, v in raw_dict.items():
                    if k.isdigit() and v.lower().strip() in ('a', 'b', 'c', 'd'):
                        answers[str(int(k))] = v.lower().strip()

                # Save corrected cache
                cache_file = CACHE_DIR / f"{year}_answers.json"
                old_answers = {}
                if cache_file.exists():
                    old_answers = json.loads(cache_file.read_text(encoding="utf-8"))

                # Show diff
                changed = 0
                for qn in sorted(answers.keys(), key=int):
                    old = old_answers.get(qn, old_answers.get(str(qn), "?"))
                    new = answers[qn]
                    if old != new:
                        changed += 1

                cache_file.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Set A: {len(answers)} answers extracted, {changed} changed from old cache")
            else:
                print(f"  Failed to parse JSON from response")
        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(3)  # respect rate limit between years

    # Now re-merge answers into raw_questions.json
    print("\n" + "=" * 60)
    print("Re-merging corrected answers into raw_questions.json...")

    raw_path = DATA_DIR / "raw_questions.json"
    if not raw_path.exists():
        print("raw_questions.json not found!")
        return

    with open(raw_path, encoding="utf-8") as f:
        questions = json.load(f)

    # Load all corrected answer caches
    all_answers = {}
    for year in YEARS_WITH_AK:
        cache_file = CACHE_DIR / f"{year}_answers.json"
        if cache_file.exists():
            year_ans = json.loads(cache_file.read_text(encoding="utf-8"))
            all_answers[year] = {int(k): v for k, v in year_ans.items()}
            print(f"  {year}: {len(year_ans)} answers loaded")

    # Apply corrected answers
    updated = 0
    for q in questions:
        year_ans = all_answers.get(q["year"], {})
        old_ans = q.get("correct_option")
        new_ans = year_ans.get(q.get("q_num"))
        q["correct_option"] = new_ans
        if old_ans != new_ans:
            updated += 1

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    print(f"\nAnswers updated: {updated} questions changed")
    print(f"Total with answers: {sum(1 for q in questions if q.get('correct_option'))}")
    print(f"\nNext: run classify_and_build_db.py to rebuild the database")


if __name__ == "__main__":
    main()
