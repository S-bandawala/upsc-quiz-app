"""
Pre-generates AI insights for 10 random questions per year (2014-2024)
using Claude Haiku with the upgraded structured prompt.

Stores results directly in upsc_beta.db (ai_explanation column).
Skips questions that already have a cached explanation.

Usage: python scripts/pregen_insights.py
       python scripts/pregen_insights.py --force   (overwrite existing)
       python scripts/pregen_insights.py --year 2022  (single year)
"""

import os, sys, json, random, time, sqlite3
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
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
YEARS    = list(range(2014, 2025))   # 2014–2024 inclusive
PER_YEAR = 100                        # all questions per year
DELAY_SEC = 0.3

# ── Parse args ─────────────────────────────────────────────────────────────────
force = "--force" in sys.argv
single_year = None
if "--year" in sys.argv:
    idx = sys.argv.index("--year")
    single_year = int(sys.argv[idx + 1])
    YEARS = [single_year]

# ── Upgraded prompt (same as compare_ai_mentor.py) ────────────────────────────
def build_prompt(q: dict) -> str:
    """Build prompt that covers ALL 3 wrong options — no assumption about student's choice."""
    correct = (q.get("correct_option") or "").strip().lower()
    wrong_opts = [l for l in ["a", "b", "c", "d"] if l != correct]

    wrong_lines = "\n".join(
        f'You may be inclined to choose ({l.upper()}) "{q.get("option_"+l,"")[:80]}" — explain in 1 sentence why this is tempting, then 1 sentence why it is wrong.'
        for l in wrong_opts
    )

    freq = q.get("frequency", 1) or 1
    freq_note = f"HIGH PRIORITY — appeared {freq} times in UPSC." if freq > 1 else ""

    return f"""You are a UPSC CSE expert mentor. A student just attempted this official UPSC question.

QUESTION (UPSC {q.get('year_first','')}, Q.{q.get('q_num','')}):
{q['question']}

(a) {q.get('option_a','')}
(b) {q.get('option_b','')}
(c) {q.get('option_c','')}
(d) {q.get('option_d','')}

Correct answer: ({correct.upper()})
Topic: {q.get('topic','')} > {q.get('subtopic','')}
{freq_note}

Write your analysis in EXACTLY these 4 sections with these exact headers:

CORRECT ANSWER: WHY ({correct.upper()}) IS RIGHT
State the single core fact or principle that makes ({correct}) right. Max 2 sentences. Be precise.

TRAP ANALYSIS
For each wrong option, write exactly 2 sentences using this framing:
{wrong_lines}

UPSC PATTERN
What specific skill does UPSC test here? How is this question type typically framed? Max 2 sentences.

LOCK IT IN
One sharp memory device — mnemonic, acronym, vivid analogy, or key contrast. Must be specific to THIS answer.

Rules:
- Total response: 150-200 words
- No filler phrases like "Great question" or "In conclusion"
- Speak directly to the student
"""


def get_haiku_insight(q: dict) -> str:
    prompt = build_prompt(q)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text.strip()


# ── Load DB ────────────────────────────────────────────────────────────────────
print("=" * 60)
print(f"Pre-generating Haiku insights: {PER_YEAR} Qs x {len(YEARS)} years = {PER_YEAR*len(YEARS)} total")
print(f"Model : {MODEL}")
print(f"Force : {force}")
print("=" * 60)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Ensure column exists
try:
    conn.execute("ALTER TABLE questions ADD COLUMN ai_explanation TEXT")
    conn.commit()
except Exception:
    pass

# ── Main loop ─────────────────────────────────────────────────────────────────
total_done = 0
total_skipped = 0
errors = []

random.seed(99)   # fixed seed — reproducible sample

for year in YEARS:
    # Fetch all Qs for this year with correct answers
    rows = conn.execute(
        "SELECT * FROM questions WHERE year_tags LIKE ? AND correct_option IS NOT NULL AND correct_option != ''",
        [f"%{year}%"]
    ).fetchall()

    if not rows:
        print(f"\n  {year}: no questions found — skipping")
        continue

    qs = [dict(r) for r in rows]
    # Parse year_tags JSON string if needed
    for q in qs:
        if isinstance(q.get("year_tags"), str):
            try:
                q["year_tags"] = json.loads(q["year_tags"])
            except Exception:
                q["year_tags"] = []

    sample = random.sample(qs, min(PER_YEAR, len(qs)))

    print(f"\n{year}  ({len(qs)} Qs available, sampling {len(sample)})")

    for i, q in enumerate(sample, 1):
        qid  = q["id"]
        qnum = q.get("q_num", "?")
        topic = q.get("topic", "")

        # Skip if already cached (unless --force)
        if not force and q.get("ai_explanation"):
            print(f"  [{i}/{len(sample)}] Q{qnum} ({topic}) — SKIP (cached)")
            total_skipped += 1
            continue

        print(f"  [{i}/{len(sample)}] Q{qnum} ({topic}) ...", end=" ", flush=True)
        t0 = time.time()
        try:
            insight = get_haiku_insight(q)
            elapsed = round(time.time() - t0, 1)
            wc = len(insight.split())
            conn.execute(
                "UPDATE questions SET ai_explanation = ? WHERE id = ?",
                [insight, qid]
            )
            conn.commit()
            print(f"{elapsed}s | {wc}w OK")
            total_done += 1
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            print(f"ERROR: {e}")
            errors.append((year, qnum, str(e)))

        if i < len(sample):
            time.sleep(DELAY_SEC)

conn.close()

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print(f"DONE")
print(f"  Generated : {total_done}")
print(f"  Skipped   : {total_skipped} (already cached)")
print(f"  Errors    : {len(errors)}")
if errors:
    for yr, qn, e in errors:
        print(f"    {yr} Q{qn}: {e}")
print("=" * 60)
print("Run the server and test — pre-cached insights load instantly.")
