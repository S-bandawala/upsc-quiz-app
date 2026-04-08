"""
UPSC GS-1 Question Extractor — Vision-based (Groq - FREE)
Uses Groq's Llama 4 Scout vision model to extract questions from image-based PDFs.
Zero cost — free tier: 30 req/min, 14,400 req/day.

REQUIRES: GROQ_API_KEY environment variable set.
  Get free key: https://console.groq.com

Output: data/raw_questions.json
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import fitz  # pymupdf — renders PDF pages to images
from groq import Groq

# ── Load .env if present ────────────────────────────────────────────────────────
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

# ── Check API key ───────────────────────────────────────────────────────────────
if not os.environ.get("GROQ_API_KEY"):
    print("ERROR: GROQ_API_KEY is not set.")
    print("  Get a free key at: https://console.groq.com")
    print("  Then add to upsc_app/.env:")
    print("    GROQ_API_KEY=gsk_...")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE_DIR.parent / "UPSC_CSP_Papers"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

YEARS = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]  # All years — cached ones load instantly, new ones extract via API

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Rate limit: 30 req/min on free tier -> 2.5 sec between requests
RATE_LIMIT_DELAY = 2.5


# ── Vision Extraction ────────────────────────────────────────────────────────────

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

ANSWER_KEY_PROMPT = """This is an official UPSC answer key document for Series/Set A.
Extract all question numbers and their correct answers from this page.
Return ONLY valid JSON: {"1": "b", "2": "a", ...}
Use lowercase a/b/c/d only. If a question was dropped/deleted, skip it.
"""


def pdf_page_to_b64(page) -> str:
    """Render a PDF page to a base64 PNG image."""
    pix = page.get_pixmap(dpi=150)
    return base64.standard_b64encode(pix.tobytes("png")).decode()


def groq_vision(b64_image: str, prompt: str) -> str:
    """Send an image + prompt to Groq vision model. Auto-retries on rate limits."""
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
                max_tokens=3000,
                temperature=0.1
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                # Parse wait time from error message
                wait = 60  # default wait
                m = re.search(r'try again in (\d+)m([\d.]+)s', err_str)
                if m:
                    wait = int(m.group(1)) * 60 + float(m.group(2)) + 5  # +5s buffer
                else:
                    m2 = re.search(r'try again in ([\d.]+)s', err_str)
                    if m2:
                        wait = float(m2.group(1)) + 5
                # If wait is over 10 min, daily limit likely hit — stop gracefully
                if wait > 600:
                    raise Exception(f"DAILY_LIMIT_HIT: wait time {wait:.0f}s suggests daily quota exhausted")
                print(f"      Rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})...", flush=True)
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Rate limit exceeded after {max_retries} retries")


def extract_questions_from_page(page, year: int, page_num: int) -> list[dict]:
    """Send one PDF page to Groq Vision and get back questions."""
    b64 = pdf_page_to_b64(page)
    try:
        raw = groq_vision(b64, EXTRACT_PROMPT)
        # Extract JSON array
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            qs = json.loads(m.group())
            for q in qs:
                q["year"] = year
                q["source_page"] = page_num
            return qs
    except json.JSONDecodeError as e:
        print(f"    Page {page_num} JSON parse error: {e}", flush=True)
    except Exception as e:
        print(f"    Page {page_num} error: {e}", flush=True)
    return []


def extract_answer_key_from_pdf(ak_path: Path, year: int) -> dict:
    """Extract answer key from image-based PDF — Set A only (page 1).
    UPSC answer keys have 4 pages: Set A, B, C, D.
    Our question papers are Set A, so we only need page 1."""
    answers = {}
    doc = fitz.open(str(ak_path))

    # Only process page 1 (Set A) — pages 2-4 are Sets B, C, D
    if doc.page_count < 1:
        return answers

    b64 = pdf_page_to_b64(doc[0])
    try:
        raw = groq_vision(b64, ANSWER_KEY_PROMPT)
        m = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if m:
            raw_dict = json.loads(m.group())
            for k, v in raw_dict.items():
                if k.isdigit() and v.lower().strip() in ('a', 'b', 'c', 'd'):
                    answers[int(k)] = v.lower().strip()
        print(f"    Set A answers extracted: {len(answers)}")
    except Exception as e:
        print(f"    AK page 1 (Set A) error: {e}")
    time.sleep(RATE_LIMIT_DELAY)

    return answers


def extract_from_pdf(pdf_path: Path, year: int) -> list[dict]:
    """Extract all questions from a GS-1 PDF."""
    doc = fitz.open(str(pdf_path))
    all_questions = []
    seen_nums = set()

    total = doc.page_count
    print(f"    Processing {total} pages...", flush=True)

    for page_num in range(2, total):  # skip cover/instructions
        page = doc[page_num]
        qs = extract_questions_from_page(page, year, page_num + 1)

        for q in qs:
            qn = q.get("q_num")
            if qn and isinstance(qn, int) and 1 <= qn <= 100 and qn not in seen_nums:
                seen_nums.add(qn)
                all_questions.append(q)

        if qs:
            nums = [q.get("q_num") for q in qs]
            print(f"    Page {page_num+1}: found Q{min(nums)}-Q{max(nums)} ({len(qs)} Qs)", flush=True)

        if len(seen_nums) >= 100:
            print(f"    All 100 questions found, stopping early.", flush=True)
            break

        time.sleep(RATE_LIMIT_DELAY)  # respect rate limit

    return sorted(all_questions, key=lambda x: x.get("q_num", 0))


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    all_questions = []
    all_answers = {}

    print("=" * 60)
    print("UPSC GS-1 Question Extractor (Groq - FREE)")
    print(f"Model: {MODEL} | Rate: 30 req/min")
    print("=" * 60)

    for year in YEARS:
        qp_path = PAPERS_DIR / str(year) / "Question_Papers" / f"UPSC_CSP_{year}_QuestionPaper_GS-Paper-I.pdf"
        ak_path = PAPERS_DIR / str(year) / "Answer_Keys" / f"UPSC_CSP_{year}_AnswerKey_GS-Paper-I.pdf"

        if not qp_path.exists():
            print(f"\n[{year}] QP NOT FOUND -- skipping")
            continue

        cache_qs = DATA_DIR / "cache" / f"{year}_questions.json"
        cache_ans = DATA_DIR / "cache" / f"{year}_answers.json"
        (DATA_DIR / "cache").mkdir(exist_ok=True)

        # Load from cache if already extracted
        if cache_qs.exists():
            print(f"\n[{year}] Loading from cache...", flush=True)
            qs = json.loads(cache_qs.read_text(encoding="utf-8"))
            ans = json.loads(cache_ans.read_text(encoding="utf-8")) if cache_ans.exists() else {}
            print(f"  TOTAL: {len(qs)} questions (cached)")
        else:
            try:
                print(f"\n[{year}] Extracting questions...", flush=True)
                qs = extract_from_pdf(qp_path, year)
                for q in qs:
                    q["source_pdf"] = qp_path.name
                print(f"  TOTAL: {len(qs)} unique questions extracted for {year}")

                if ak_path.exists():
                    print(f"[{year}] Extracting answer key...", flush=True)
                    ans = extract_answer_key_from_pdf(ak_path, year)
                    print(f"  TOTAL: {len(ans)} answers extracted")
                else:
                    print(f"[{year}] No answer key available")
                    ans = {}

                # Save per-year cache
                cache_qs.write_text(json.dumps(qs, ensure_ascii=False, indent=2), encoding="utf-8")
                cache_ans.write_text(json.dumps(ans, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                if "DAILY_LIMIT_HIT" in str(e):
                    print(f"\n*** DAILY LIMIT HIT during {year} — saving partial progress and stopping ***", flush=True)
                    # Save partial cache if we got any questions
                    if qs:
                        cache_qs.write_text(json.dumps(qs, ensure_ascii=False, indent=2), encoding="utf-8")
                    break
                raise

        all_questions.extend(qs)
        all_answers[year] = ans

        # Save merged JSON after each year
        out_path = DATA_DIR / "raw_questions.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_questions, f, ensure_ascii=False, indent=2)

    # Attach correct answers
    for q in all_questions:
        year_ans = all_answers.get(q["year"], {})
        q["correct_option"] = year_ans.get(q.get("q_num"), None)

    # Save final
    out_path = DATA_DIR / "raw_questions.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"Total questions extracted : {len(all_questions)}")
    print(f"With correct answers      : {sum(1 for q in all_questions if q.get('correct_option'))}")
    print(f"Output                    : {out_path}")
    print("Next step: run classify_and_build_db.py")


if __name__ == "__main__":
    main()
