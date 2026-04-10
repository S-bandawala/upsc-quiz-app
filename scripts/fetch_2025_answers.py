"""
Fetches answers for UPSC 2025 questions using Claude Haiku.

Claude Haiku (trained through Oct 2025) has knowledge of the UPSC 2025 answer key
which was published by UPSC in May-June 2025.

For each question, Haiku determines the most likely correct answer based on:
1. Its training knowledge of the official/coaching institute answer keys
2. Subject matter expertise for factual recall questions

Stored with answer_source='ai_estimate'. Once UPSC official key is available,
run with --official answers.json to override with verified answers.

Usage:
  python scripts/fetch_2025_answers.py              # process all 100 2025 Qs
  python scripts/fetch_2025_answers.py --official answers.json  # apply official key
"""

import os, sys, json, time, sqlite3, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

import anthropic
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-haiku-4-5-20251001"
DB_PATH = BASE_DIR / "data" / "upsc_beta.db"
DELAY_SEC = 0.3

DISCLAIMER = (
    "\n\n⚠️ NOTE: This answer is based on AI knowledge (UPSC 2025 key was published "
    "May-June 2025). Once you have the official PDF, run: "
    "python scripts/fetch_2025_answers.py --official answers.json"
)

# ── DB setup ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

for col, typedef in [("answer_source","TEXT"), ("consensus_count","INTEGER")]:
    try:
        conn.execute(f"ALTER TABLE questions ADD COLUMN {col} {typedef}")
        conn.commit()
    except Exception:
        pass


# ── Handle --official mode ────────────────────────────────────────────────────
if "--official" in sys.argv:
    idx = sys.argv.index("--official")
    key_file = Path(sys.argv[idx+1])
    with open(key_file, encoding="utf-8") as f:
        official = json.load(f)   # {q_num: "a"|"b"|"c"|"d"}
    updated = 0
    for q_num, ans in official.items():
        conn.execute(
            "UPDATE questions SET correct_option=?, answer_source='official', consensus_count=NULL, ai_explanation=NULL WHERE year_first=2025 AND q_num=?",
            [ans.lower(), int(q_num)]
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"Updated {updated} questions with official answers. AI insights cleared for re-generation.")
    print("Now re-run: python scripts/pregen_insights.py --year 2025 --force")
    sys.exit(0)


# ── Ask Haiku to identify the correct answer ──────────────────────────────────
def get_answer(q: dict) -> tuple[str, str]:
    """Returns (option_letter, confidence: high|medium|low)."""
    prompt = f"""UPSC 2025 GS Paper I question. Give ONLY the answer letter and confidence.

Q.{q['q_num']}: {q['question']}

(a) {q.get('option_a','')}
(b) {q.get('option_b','')}
(c) {q.get('option_c','')}
(d) {q.get('option_d','')}

Your FIRST line MUST be: ANSWER: a  (or b, c, d)
Your SECOND line MUST be: CONFIDENCE: high  (or medium, low)
Your THIRD line MUST be: REASON: one sentence

Do NOT include any other text before ANSWER:"""
    resp = client.messages.create(
        model=MODEL, max_tokens=120, temperature=0,
        messages=[
            {"role":"user","content":prompt},
            {"role":"assistant","content":"ANSWER:"}
        ]
    )
    text = ("ANSWER:" + resp.content[0].text).strip()
    ans_m  = re.search(r'ANSWER:\s*\(?([abcd])\)?', text, re.IGNORECASE)
    conf_m = re.search(r'CONFIDENCE:\s*(high|medium|low)', text, re.IGNORECASE)
    ans    = ans_m.group(1).lower() if ans_m else ''
    conf   = conf_m.group(1).lower() if conf_m else 'low'
    return ans, conf


# ── Generate insight ──────────────────────────────────────────────────────────
def generate_insight(q: dict, correct: str, confidence: str) -> str:
    wrong_opts = [l for l in ["a","b","c","d"] if l != correct]
    wrong_lines = "\n".join(
        f'You may be inclined to choose ({l.upper()}) "{q.get("option_"+l,"")[:80]}" — explain in 1 sentence why this is tempting, then 1 sentence why it is wrong.'
        for l in wrong_opts
    )
    conf_note = {
        "high":   "Answer confidence: HIGH — strongly supported by factual knowledge.",
        "medium": "Answer confidence: MEDIUM — based on reasoning; verify when official key is released.",
        "low":    "Answer confidence: LOW — uncertain; treat as tentative until official key is released."
    }[confidence]

    prompt = f"""You are a UPSC CSE expert mentor.

QUESTION (UPSC 2025, Q.{q.get('q_num','')}):
{q['question']}

(a) {q.get('option_a','')}
(b) {q.get('option_b','')}
(c) {q.get('option_c','')}
(d) {q.get('option_d','')}

Most likely correct answer: ({correct.upper()}) [{conf_note}]
Topic: {q.get('topic','')} > {q.get('subtopic','')}

Write your analysis in EXACTLY these 4 sections:

CORRECT ANSWER: WHY ({correct.upper()}) IS RIGHT
State the single core fact or principle. Max 2 sentences.

TRAP ANALYSIS
{wrong_lines}

UPSC PATTERN
What skill does UPSC test here? Max 2 sentences.

LOCK IT IN
One sharp mnemonic specific to THIS answer.

Rules: 150-200 words total. No filler. Speak directly to the student.
"""
    resp = client.messages.create(
        model=MODEL, max_tokens=500, temperature=0.3,
        messages=[{"role":"user","content":prompt}]
    )
    insight = resp.content[0].text.strip()

    disclaimer = f"\n\n⚠️ 2025 Answer ({conf_note}) — Official UPSC key expected May–June 2026. This will auto-update once verified."
    return insight + disclaimer


# ── Main ──────────────────────────────────────────────────────────────────────
rows = conn.execute(
    "SELECT * FROM questions WHERE year_first=2025 AND (correct_option IS NULL OR correct_option='') ORDER BY q_num"
).fetchall()
qs = [dict(r) for r in rows]

print("="*60)
print(f"UPSC 2025 Answer Finder — Claude Haiku")
print(f"Questions to process: {len(qs)}")
print("="*60)

done = skipped = failed = 0

for i, q in enumerate(qs, 1):
    qnum = q["q_num"]
    topic = q.get("topic","")

    if q.get("answer_source") in ("official","web_consensus","ai_estimate"):
        print(f"[{i}/{len(qs)}] Q{qnum} SKIP ({q['answer_source']})")
        skipped += 1
        continue

    print(f"[{i}/{len(qs)}] Q{qnum} ({topic}) ...", end=" ", flush=True)
    t0 = time.time()

    ans, conf = get_answer(q)
    if not ans:
        print(f"FAILED — no answer extracted")
        failed += 1
        time.sleep(DELAY_SEC)
        continue

    insight = generate_insight(q, ans, conf)
    elapsed = round(time.time()-t0, 1)
    wc = len(insight.split())
    print(f"({ans.upper()}) [{conf}] {elapsed}s | {wc}w OK")

    conn.execute("""
        UPDATE questions
        SET correct_option=?, answer_source='ai_estimate', consensus_count=NULL, ai_explanation=?
        WHERE id=?
    """, [ans, insight, q["id"]])
    conn.commit()
    done += 1
    time.sleep(DELAY_SEC)

conn.close()

print()
print("="*60)
print(f"DONE  |  Processed: {done}  |  Skipped: {skipped}  |  Failed: {failed}")
print()
print("When official UPSC 2025 key is available:")
print("  python scripts/fetch_2025_answers.py --official answers.json")
print("="*60)
