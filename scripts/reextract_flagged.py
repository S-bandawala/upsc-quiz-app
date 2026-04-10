"""
Re-extract flagged questions using improved prompt.
Only sends the specific PDF pages containing flagged questions to Groq Vision.
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

# Use the same improved prompt from extract_questions.py
EXTRACT_PROMPT = """This is a page from an official UPSC Civil Services Preliminary Examination
GS Paper-I question paper.

Extract ALL English-language questions visible on this page.
Return ONLY a JSON array, no explanation.

IMPORTANT — UPSC questions have TWO parts:
1. QUESTION BODY: The main question text INCLUDING any numbered sub-statements
   like "1. ...", "2. ...", "3. ..." AND any follow-up line like
   "Which of the above statements is/are correct?" or "Select the correct answer using the code below:"
   ALL of this goes into the "question" field as one string.

2. ANSWER CHOICES: Always exactly 4 options marked as (a), (b), (c), (d) at the
   bottom of each question. These are the ONLY things that go into option_a/b/c/d.

Example — for a question that looks like:
  "Consider the following statements:
   1. Statement one
   2. Statement two
   Which of the above is/are correct?
   (a) 1 only  (b) 2 only  (c) Both 1 and 2  (d) Neither 1 nor 2"

The correct extraction is:
  "question": "Consider the following statements: 1. Statement one 2. Statement two Which of the above is/are correct?",
  "option_a": "1 only",
  "option_b": "2 only",
  "option_c": "Both 1 and 2",
  "option_d": "Neither 1 nor 2"

NEVER put numbered sub-statements (1., 2., 3.) as options.
Options are ALWAYS the (a), (b), (c), (d) choices at the end of each question.

CRITICAL — Many UPSC questions span MULTIPLE lines with lists, pairs, or tables like:
  "Consider the following pairs:
   Tradition          State
   1. Chapchar Kut    Mizoram
   2. Khongjom Parba  Manipur
   3. Thang-Ta        Sikkim
   Which of the pairs given above is/are correctly matched?"

You MUST capture the ENTIRE content including the list/pairs/table inside the "question" field.
DO NOT return just the header line like "Consider the following pairs:" — that is INCOMPLETE.
The full list of items (1., 2., 3. etc.) and the follow-up line MUST be included.

Format:
[
  {
    "q_num": 1,
    "question": "full question text with all sub-statements included",
    "option_a": "(a) choice text only",
    "option_b": "(b) choice text only",
    "option_c": "(c) choice text only",
    "option_d": "(d) choice text only"
  }
]

Rules:
- Include ONLY English questions (skip Hindi text entirely)
- q_num is the question number (1-100)
- Each question MUST have all 4 options (a/b/c/d). If you cannot find all 4, look harder on the page.
- If no English questions on this page, return []
- Clean up any OCR artifacts like ~ or stray characters
"""


def pdf_page_to_b64(page) -> str:
    pix = page.get_pixmap(dpi=200)
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
                if wait > 600:
                    raise Exception(f"DAILY_LIMIT_HIT: wait time {wait:.0f}s")
                print(f"    Rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})...", flush=True)
                time.sleep(wait)
            else:
                raise
    raise Exception("Rate limit exceeded after max retries")


def find_page_for_question(doc, q_num, year):
    """Return ALL pages in the PDF (skip cover page 0 and 1).
    Previous narrow estimation missed many questions, so now we scan everything."""
    return list(range(2, doc.page_count))


def main():
    print("=" * 60)
    print("Re-extract Flagged Questions (Improved Prompt)")
    print("=" * 60)

    # Load flagged questions
    flagged_path = DATA_DIR / "flagged_questions.json"
    with open(flagged_path, encoding="utf-8") as f:
        flagged = json.load(f)

    # Skip the instructions page entry (2015 Q1 — not a real question)
    flagged = [q for q in flagged if q.get("_flagged") != "instructions_page"]

    print(f"Flagged questions to re-extract: {len(flagged)}")

    # Group by year
    by_year = {}
    for q in flagged:
        yr = q.get("year_first", q.get("year"))
        by_year.setdefault(yr, []).append(q.get("q_num"))

    for yr in sorted(by_year):
        by_year[yr] = sorted(set(by_year[yr]))
        print(f"  {yr}: Q{by_year[yr]}")

    # Load existing beta_questions for merging later
    beta_path = DATA_DIR / "beta_questions.json"
    with open(beta_path, encoding="utf-8") as f:
        beta_qs = json.load(f)

    # Load answer caches
    all_answers = {}
    cache_dir = DATA_DIR / "cache"
    for ans_file in cache_dir.glob("*_answers.json"):
        yr = int(ans_file.stem.split("_")[0])
        ans = json.loads(ans_file.read_text(encoding="utf-8"))
        all_answers[yr] = {int(k): v for k, v in ans.items()}

    # Process each year
    fixed = []
    still_bad = []
    api_calls = 0

    for year in sorted(by_year):
        q_nums = by_year[year]
        qp_path = PAPERS_DIR / str(year) / "Question_Papers" / f"UPSC_CSP_{year}_QuestionPaper_GS-Paper-I.pdf"

        if not qp_path.exists():
            print(f"\n[{year}] QP not found — skipping")
            continue

        doc = fitz.open(str(qp_path))
        print(f"\n[{year}] Extracting {len(q_nums)} questions from {doc.page_count}-page PDF...")

        # Track which pages we've already processed
        processed_pages = set()
        extracted_by_qnum = {}

        for q_num in q_nums:
            if q_num in extracted_by_qnum:
                continue  # already got it from a previous page scan

            candidate_pages = find_page_for_question(doc, q_num, year)

            for page_idx in candidate_pages:
                if page_idx in processed_pages:
                    # Check if we already found this q_num
                    if q_num in extracted_by_qnum:
                        break
                    continue

                processed_pages.add(page_idx)
                b64 = pdf_page_to_b64(doc[page_idx])

                try:
                    raw = groq_vision(b64, EXTRACT_PROMPT)
                    api_calls += 1

                    # Parse JSON
                    m = re.search(r'\[.*\]', raw, re.DOTALL)
                    if m:
                        questions = json.loads(m.group())
                        for q in questions:
                            qn = q.get("q_num")
                            if qn:
                                extracted_by_qnum[qn] = q
                                extracted_by_qnum[qn]["year"] = year

                        found_nums = [q.get("q_num") for q in questions if q.get("q_num")]
                        print(f"  Page {page_idx+1}: found Q{found_nums}", flush=True)
                except Exception as e:
                    if "DAILY_LIMIT_HIT" in str(e):
                        print(f"\n*** DAILY LIMIT HIT — stopping. Fixed {len(fixed)} so far. ***")
                        # Save partial progress
                        _save_results(fixed, still_bad, flagged, beta_qs, all_answers)
                        return
                    print(f"  Page {page_idx+1} error: {e}")

                time.sleep(3)  # rate limit

                if q_num in extracted_by_qnum:
                    break  # found it, move to next q_num

        # Check results for this year
        for q_num in q_nums:
            if q_num in extracted_by_qnum:
                q = extracted_by_qnum[q_num]
                opts = [q.get("option_a",""), q.get("option_b",""), q.get("option_c",""), q.get("option_d","")]
                missing = [i for i, o in enumerate(opts) if not o or not o.strip()]

                if missing:
                    print(f"  Q{q_num}: STILL BAD (missing options {missing})")
                    still_bad.append({"year": year, "q_num": q_num, "data": q})
                else:
                    # Attach answer from cache
                    q["correct_option"] = all_answers.get(year, {}).get(q_num)
                    q["year_first"] = year
                    q["source_pdfs"] = [f"UPSC_CSP_{year}_QuestionPaper_GS-Paper-I.pdf"]
                    print(f"  Q{q_num}: FIXED (answer={q.get('correct_option')})")
                    fixed.append(q)
            else:
                print(f"  Q{q_num}: NOT FOUND on any page")
                still_bad.append({"year": year, "q_num": q_num, "data": None})

    _save_results(fixed, still_bad, flagged, beta_qs, all_answers)


def _save_results(fixed, still_bad, flagged, beta_qs, all_answers):
    print(f"\n{'='*60}")
    print(f"Results: {len(fixed)} fixed, {len(still_bad)} still bad")

    if not fixed:
        print("Nothing to merge.")
        return

    # Merge fixed questions into beta_questions
    # First remove any existing entries with same year+q_num (to avoid duplicates)
    fixed_keys = {(q["year_first"], q.get("q_num")) for q in fixed}
    beta_qs = [q for q in beta_qs if (q.get("year_first"), q.get("q_num")) not in fixed_keys]

    # Add fixed questions (need classification — use "Current Affairs" as default)
    for q in fixed:
        q.setdefault("topic", "Current Affairs")
        q.setdefault("subtopic", "")
        q.setdefault("difficulty", "medium")
        q.setdefault("frequency", 1)
        q.setdefault("is_repeated", 0)
        q.setdefault("year_tags", [q["year_first"]])

    beta_qs.extend(fixed)

    # Re-number IDs
    for i, q in enumerate(beta_qs, 1):
        q["id"] = i

    # Save
    beta_path = DATA_DIR / "beta_questions.json"
    with open(beta_path, "w", encoding="utf-8") as f:
        json.dump(beta_qs, f, ensure_ascii=False, indent=2)
    print(f"Updated beta_questions.json: {len(beta_qs)} questions")

    # Update flagged list to only contain still_bad
    remaining_flagged = [{"year": s["year"], "q_num": s["q_num"], "reason": "re-extraction_failed"}
                         for s in still_bad]
    # Keep the instructions_page entry
    remaining_flagged.append({"year": 2015, "q_num": 1, "reason": "instructions_page"})

    with open(DATA_DIR / "reextract_priority.json", "w", encoding="utf-8") as f:
        json.dump(remaining_flagged, f, ensure_ascii=False, indent=2)

    with open(DATA_DIR / "flagged_questions.json", "w", encoding="utf-8") as f:
        json.dump(remaining_flagged, f, ensure_ascii=False, indent=2)
    print(f"Remaining flagged: {len(remaining_flagged)}")
    print(f"\nNext: run rebuild_db.py to update the database")


if __name__ == "__main__":
    main()
