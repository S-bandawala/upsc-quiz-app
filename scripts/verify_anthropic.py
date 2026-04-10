"""
UPSC Question Verifier using Anthropic Claude Vision API.
Verifies a specific year's questions against the original PDF (verbatim).
Shows all text differences and fixes them in beta_questions.json.

Usage: python scripts/verify_anthropic.py 2016
"""

import anthropic
import base64
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
import fitz

# ── Load .env ──────────────────────────────────────────────────────────────────
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set"); sys.exit(1)

BASE_DIR   = Path(__file__).resolve().parent.parent
PAPERS_DIR = BASE_DIR.parent / "UPSC_CSP_Papers"
DATA_DIR   = BASE_DIR / "data"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL  = "claude-haiku-4-5-20251001"   # cheapest, still very accurate for OCR

VERIFY_PROMPT = """This is a page from an official UPSC Civil Services Preliminary Examination GS Paper-I question paper.

Extract ALL English-language questions visible on this page.
Return ONLY a JSON array — no explanation, no markdown fences.

== CRITICAL: VERBATIM COPY ==
Copy EVERY word EXACTLY as printed. Do NOT change, simplify, or substitute any word.
- "Scheduled Commercial Banks" must stay "Scheduled Commercial Banks" — NOT "commercial banks"
- "aggregate money supply" must stay "aggregate money supply" — NOT "money supply"
- Proper nouns, technical terms, acronyms — copy letter-for-letter.

== QUESTION STRUCTURE ==
1. QUESTION BODY: Everything from the question number up to and including the
   final instruction line ("Which of the above is/are correct?" etc).
   This includes all numbered sub-statements (1. 2. 3.) and any pairs/tables.
   Put ALL of this in the "question" field as one string.

2. OPTIONS: Exactly 4 choices marked (a) (b) (c) (d) at the end of each question.
   These go into option_a / option_b / option_c / option_d.
   Do NOT strip the (a)/(b)/(c)/(d) prefix from options.
   Do NOT put numbered sub-statements (1. 2. 3.) as options.

== FOR MULTI-LINE QUESTIONS ==
"Consider the following pairs/statements" questions span many lines.
You MUST include the FULL list — every pair/row/statement — not just the header.

== FORMAT ==
[
  {
    "q_num": 1,
    "question": "full verbatim question text including all sub-statements",
    "option_a": "(a) exact choice text",
    "option_b": "(b) exact choice text",
    "option_c": "(c) exact choice text",
    "option_d": "(d) exact choice text"
  }
]

Rules:
- Include ONLY English questions (skip Hindi text entirely)
- q_num is the integer question number (1-100)
- Every question MUST have all 4 options; if options continue on next page mark them ""
- If no English questions on this page, return []
"""


def page_to_b64(page) -> str:
    pix = page.get_pixmap(dpi=150)
    return base64.standard_b64encode(pix.tobytes("png")).decode()


def claude_vision(b64: str) -> list:
    """Send one page image to Claude, return parsed list of question dicts."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64
                    }
                },
                {"type": "text", "text": VERIFY_PROMPT}
            ]
        }]
    )
    raw = resp.choices[0].message.content if hasattr(resp, 'choices') else resp.content[0].text
    # Parse JSON
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


def extract_year(year: int) -> list:
    """Extract all questions from a year's PDF using Claude Vision."""
    qp_dir = PAPERS_DIR / str(year) / "Question_Papers"
    pdf_path = None
    for f in qp_dir.iterdir():
        if "GS-Paper-I" in f.name and f.suffix == ".pdf":
            pdf_path = f
            break

    if not pdf_path:
        print(f"PDF not found for {year}"); return []

    doc = fitz.open(str(pdf_path))
    print(f"PDF: {pdf_path.name}  ({doc.page_count} pages)")

    all_qs = {}
    for pg_idx in range(doc.page_count):
        b64 = page_to_b64(doc[pg_idx])
        qs = claude_vision(b64)

        new = 0
        for q in qs:
            qn = q.get('q_num')
            if qn and qn not in all_qs:
                if all(q.get(f'option_{x}', '').strip() for x in 'abcd'):
                    q['year'] = year
                    all_qs[qn] = q
                    new += 1

        if new:
            print(f"  Page {pg_idx+1:2d}: +{new} Qs  (running total: {len(all_qs)})")

        if len(all_qs) >= 100:
            print(f"  All 100 questions found — stopping early.")
            break

    doc.close()
    return list(all_qs.values())


def compare(verified: list, existing: list, year: int):
    """Compare verified vs existing, print diffs, apply fixes. Returns counts."""
    ex_map = {q['q_num']: q for q in existing if q.get('year') == year}

    changes, recovered = [], []

    for vq in verified:
        qn = vq['q_num']
        if qn not in ex_map:
            recovered.append(qn)
            continue

        eq = ex_map[qn]
        diffs = []

        def clean(s):
            return re.sub(r'\s+', ' ', str(s)).strip()

        # Compare question text
        if clean(vq['question']) != clean(eq['question']):
            diffs.append(('question', eq['question'], vq['question']))

        # Compare options — strip leading (a)/(b)/(c)/(d) for comparison
        for opt, letter in [('option_a','a'),('option_b','b'),('option_c','c'),('option_d','d')]:
            v_val = clean(vq.get(opt, ''))
            e_val = clean(eq.get(opt, ''))
            # Normalise: strip (a) prefix from new value for fair comparison
            v_bare = re.sub(r'^\([a-d]\)\s*', '', v_val)
            e_bare = re.sub(r'^\([a-d]\)\s*', '', e_val)
            if v_bare and e_bare and v_bare.lower() != e_bare.lower():
                diffs.append((opt, e_val, v_val))

        if diffs:
            changes.append({'q_num': qn, 'diffs': diffs})
            # Apply fix
            eq['question'] = vq['question']
            for opt in ['option_a','option_b','option_c','option_d']:
                v = vq.get(opt,'').strip()
                if v:
                    # Store without (a)/(b) prefix — consistent with rest of DB
                    eq[opt] = re.sub(r'^\([a-d]\)\s*', '', v)

    return changes, recovered


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2016
    print("=" * 60)
    print(f"Verifying {year} questions via Anthropic Claude Vision")
    print("=" * 60)

    # Load existing
    beta_path = DATA_DIR / "beta_questions.json"
    with open(beta_path, 'r', encoding='utf-8') as f:
        all_qs = json.load(f)

    year_qs = [q for q in all_qs if q.get('year') == year]
    print(f"Existing {year} questions in DB: {len(year_qs)}")
    print()

    # Extract from PDF
    print(f"Extracting from PDF...")
    verified = extract_year(year)
    print(f"\nExtracted {len(verified)} questions from PDF")
    print()

    if not verified:
        print("Nothing extracted — check PDF path."); return

    # Compare
    print("=" * 60)
    print("TEXT DIFFERENCES FOUND:")
    print("=" * 60)

    changes, recovered = compare(verified, all_qs, year)

    if not changes:
        print("  No text differences found! Extraction was accurate.")
    else:
        for c in changes:
            print(f"\n  {year} Q{c['q_num']}:")
            for field, old, new in c['diffs']:
                # Strip (a)/(b) prefix from new for display
                new_display = re.sub(r'^\([a-d]\)\s*', '', new)
                if old.strip() == new_display.strip():
                    continue
                print(f"    [{field}]")
                print(f"      OLD: {old[:120]}")
                print(f"      NEW: {new_display[:120]}")

    if recovered:
        print(f"\nRECOVERED MISSING Qs: {recovered}")
        for vq in verified:
            if vq['q_num'] in recovered:
                vq['correct_option'] = ''
                vq['topic'] = 'Current Affairs'
                vq['subtopic'] = ''
                vq['difficulty'] = 'medium'
                all_qs.append(vq)

    # Save
    all_qs.sort(key=lambda q: (q['year'], q['q_num']))
    with open(beta_path, 'w', encoding='utf-8') as f:
        json.dump(all_qs, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 60)
    print(f"SUMMARY FOR {year}:")
    print(f"  Questions verified : {len(verified)}")
    print(f"  Text fixes applied : {len(changes)}")
    print(f"  Missing Qs recovered: {len(recovered)}")
    print(f"  Total in DB now    : {len(all_qs)}")
    print("=" * 60)
    print(f"\nbeta_questions.json updated.")


if __name__ == "__main__":
    main()
