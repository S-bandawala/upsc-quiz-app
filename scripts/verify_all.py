"""
UPSC Question Verifier — Re-extracts ALL questions from PDFs and compares
with existing beta_questions.json. Fixes any mismatches (hallucinated/changed words).

Uses Groq Vision free tier. Saves progress per-year to handle rate limits.
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import fitz
from groq import Groq

# ── Load .env ──────────────────────────────────────────────────────────────────
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

if not os.environ.get("GROQ_API_KEY"):
    print("ERROR: GROQ_API_KEY not set"); sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE_DIR.parent / "UPSC_CSP_Papers"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
VERIFY_DIR = DATA_DIR / "verify_cache"
VERIFY_DIR.mkdir(exist_ok=True)

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
RATE_LIMIT_DELAY = 2.5

YEARS = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]

VERIFY_PROMPT = """This is a page from an official UPSC Civil Services Preliminary Examination
GS Paper-I question paper.

Extract ALL English-language questions visible on this page.
Return ONLY a JSON array, no explanation.

CRITICAL INSTRUCTION: Copy the text EXACTLY as printed on the page. Do NOT
paraphrase, rephrase, simplify, or substitute any words. Every single word
must match the original document VERBATIM.

For example:
- If the paper says "Scheduled Commercial Banks", write EXACTLY that — NOT "commercial banks" or "unregulated commercial banks"
- If the paper says "aggregate money supply", write EXACTLY "aggregate money supply" — NOT just "money supply"
- If the paper says a specific name, term, or phrase, copy it LETTER FOR LETTER

UPSC questions have TWO parts:
1. QUESTION BODY: The main question text INCLUDING any numbered sub-statements
   like "1. ...", "2. ...", "3. ..." AND any follow-up line like
   "Which of the above statements is/are correct?"
   ALL of this goes into the "question" field as one string.

2. ANSWER CHOICES: Always exactly 4 options marked as (a), (b), (c), (d).
   These go into option_a/b/c/d.

NEVER put numbered sub-statements (1., 2., 3.) as options.
Options are ALWAYS the (a), (b), (c), (d) choices.

CRITICAL — Many questions span MULTIPLE lines with lists, pairs, or tables.
You MUST capture the ENTIRE content including lists/pairs/tables.
DO NOT return just headers like "Consider the following pairs:" — include the FULL list.

Format:
[
  {
    "q_num": 1,
    "question": "full VERBATIM question text with all sub-statements",
    "option_a": "exact (a) choice text",
    "option_b": "exact (b) choice text",
    "option_c": "exact (c) choice text",
    "option_d": "exact (d) choice text"
  }
]

Rules:
- ONLY English questions (skip Hindi)
- q_num is 1-100
- Each question MUST have all 4 options
- If no English questions on this page, return []
- VERBATIM text — do NOT change even a single word
"""


def pdf_page_to_b64(page) -> str:
    pix = page.get_pixmap(dpi=150)
    return base64.standard_b64encode(pix.tobytes("png")).decode()


def groq_vision(b64_image, prompt):
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
                temperature=0.0  # Zero temp for exact copying
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
                    raise Exception(f"DAILY_LIMIT_HIT: wait={wait:.0f}s")

                print(f"    Rate limited, waiting {wait:.0f}s (attempt {attempt+1})...")
                time.sleep(wait)
            else:
                print(f"    Error: {err_str[:100]}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    raise
    raise Exception("Max retries exceeded")


def parse_json_response(text):
    """Extract JSON array from response text."""
    # Try to find JSON array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Try cleaning markdown
    cleaned = re.sub(r'```json\s*', '', text)
    cleaned = re.sub(r'```\s*', '', cleaned)
    match = re.search(r'\[.*\]', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


def extract_year(year):
    """Extract all questions from a year's PDF."""
    cache_file = VERIFY_DIR / f"{year}_verified.json"
    if cache_file.exists():
        print(f"  {year}: Loading from verify cache")
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    # Find PDF
    qp_dir = PAPERS_DIR / str(year) / "Question_Papers"
    pdf_path = None
    if qp_dir.exists():
        for f in qp_dir.iterdir():
            if "GS-Paper-I" in f.name and f.suffix == ".pdf":
                pdf_path = f
                break

    if not pdf_path:
        print(f"  {year}: PDF not found, skipping")
        return []

    print(f"  {year}: Extracting from {pdf_path.name} ({fitz.open(str(pdf_path)).page_count} pages)")
    doc = fitz.open(str(pdf_path))
    all_questions = []
    seen_qnums = set()

    for pg_idx in range(doc.page_count):
        b64 = pdf_page_to_b64(doc[pg_idx])
        time.sleep(RATE_LIMIT_DELAY)

        try:
            raw = groq_vision(b64, VERIFY_PROMPT)
        except Exception as e:
            if "DAILY_LIMIT_HIT" in str(e):
                raise
            print(f"    Page {pg_idx+1}: Error - {str(e)[:80]}")
            continue

        questions = parse_json_response(raw)
        if not questions:
            continue

        new_on_page = 0
        for q in questions:
            qn = q.get('q_num')
            if qn and qn not in seen_qnums:
                # Validate has all 4 options
                if all(q.get(f'option_{x}', '').strip() for x in 'abcd'):
                    q['year'] = year
                    q['source_page'] = pg_idx
                    all_questions.append(q)
                    seen_qnums.add(qn)
                    new_on_page += 1

        if new_on_page > 0:
            print(f"    Page {pg_idx+1}: +{new_on_page} Qs (total: {len(all_questions)})")

        # Early exit if we have all 100
        if len(seen_qnums) >= 100:
            print(f"    All 100 questions found!")
            break

    doc.close()

    # Save to verify cache
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_questions, f, indent=2, ensure_ascii=False)
    print(f"  {year}: {len(all_questions)} questions extracted and cached")
    return all_questions


def compare_and_fix(verified_qs, existing_qs):
    """Compare verified extraction with existing beta_questions and report/fix differences."""
    # Index existing by (year, q_num)
    existing_map = {}
    for q in existing_qs:
        key = (q['year'], q['q_num'])
        existing_map[key] = q

    changes = []
    new_qs = []

    for vq in verified_qs:
        key = (vq['year'], vq['q_num'])
        if key not in existing_map:
            new_qs.append(vq)
            continue

        eq = existing_map[key]
        diffs = []

        # Compare question text
        if vq['question'].strip() != eq['question'].strip():
            diffs.append(('question', eq['question'][:80], vq['question'][:80]))

        # Compare options
        for opt in ['option_a', 'option_b', 'option_c', 'option_d']:
            v_val = vq.get(opt, '').strip()
            e_val = eq.get(opt, '').strip()
            if v_val and e_val and v_val != e_val:
                diffs.append((opt, e_val, v_val))

        if diffs:
            changes.append({
                'year': vq['year'],
                'q_num': vq['q_num'],
                'diffs': diffs
            })
            # Apply fixes — update existing question with verified text
            eq['question'] = vq['question']
            for opt in ['option_a', 'option_b', 'option_c', 'option_d']:
                if vq.get(opt, '').strip():
                    eq[opt] = vq[opt]

    return changes, new_qs


def main():
    print("=" * 60)
    print("UPSC Question Verifier — Full Re-extraction & Comparison")
    print("=" * 60)
    print(f"Years: {YEARS}")
    print(f"Verify cache: {VERIFY_DIR}")
    print()

    # Load existing questions
    beta_path = DATA_DIR / "beta_questions.json"
    with open(beta_path, 'r', encoding='utf-8') as f:
        existing_qs = json.load(f)
    print(f"Existing questions: {len(existing_qs)}")
    print()

    all_verified = []
    daily_limit = False

    for year in YEARS:
        try:
            qs = extract_year(year)
            all_verified.extend(qs)
        except Exception as e:
            if "DAILY_LIMIT_HIT" in str(e):
                print(f"\n*** DAILY LIMIT HIT during {year} ***")
                print("Saving partial progress...")
                daily_limit = True
                break
            else:
                print(f"  {year}: Unexpected error: {e}")
                continue

    print(f"\nTotal verified: {len(all_verified)} questions")
    print()

    # Compare and fix
    if all_verified:
        print("=" * 60)
        print("Comparing with existing questions...")
        print("=" * 60)

        changes, new_qs = compare_and_fix(all_verified, existing_qs)

        if changes:
            print(f"\n*** {len(changes)} QUESTIONS HAD TEXT DIFFERENCES (FIXED) ***\n")
            for c in changes:
                print(f"  {c['year']} Q{c['q_num']}:")
                for field, old, new in c['diffs']:
                    print(f"    {field}:")
                    print(f"      OLD: {old}")
                    print(f"      NEW: {new}")
                print()
        else:
            print("\nNo text differences found!")

        if new_qs:
            print(f"\n{len(new_qs)} NEW questions found (not in existing set)")
            for nq in new_qs:
                print(f"  {nq['year']} Q{nq['q_num']}")
            # Add new questions to existing
            for nq in new_qs:
                nq['correct_option'] = ''
                nq['topic'] = 'Current Affairs'
                nq['subtopic'] = ''
                nq['difficulty'] = 'medium'
                existing_qs.append(nq)

        # Save updated beta_questions.json
        # Sort by year, then q_num
        existing_qs.sort(key=lambda q: (q['year'], q['q_num']))

        with open(beta_path, 'w', encoding='utf-8') as f:
            json.dump(existing_qs, f, indent=2, ensure_ascii=False)
        print(f"\nSaved updated beta_questions.json ({len(existing_qs)} questions)")

        # Save change log
        log_path = DATA_DIR / "verification_changes.json"
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump({
                'total_verified': len(all_verified),
                'changes_count': len(changes),
                'new_count': len(new_qs),
                'daily_limit_hit': daily_limit,
                'changes': [
                    {
                        'year': c['year'],
                        'q_num': c['q_num'],
                        'diffs': [{'field': d[0], 'old': d[1], 'new': d[2]} for d in c['diffs']]
                    }
                    for c in changes
                ]
            }, f, indent=2, ensure_ascii=False)
        print(f"Change log saved to {log_path}")

    if daily_limit:
        print("\n*** Run this script again tomorrow to continue with remaining years ***")

    print("\nDone!")


if __name__ == "__main__":
    main()
