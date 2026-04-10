"""
Reclassifies topic/subtopic for questions that landed in 'Current Affairs'
(2024 and 2025 were never properly classified after extraction).

Uses Claude Haiku for fast, cheap classification.

Usage:
  python scripts/reclassify_topics.py           # fix 2024 & 2025
  python scripts/reclassify_topics.py --year 2024
"""

import os, sys, re, time, sqlite3
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
DELAY_SEC = 0.2

TOPICS = {
    "History":      ["Ancient India", "Medieval India", "Modern India", "Indian Art & Culture", "Post-Independence India"],
    "Geography":    ["Physical Geography", "Indian Geography", "World Geography", "Climate & Monsoon", "Rivers & Water Bodies", "Resources & Agriculture"],
    "Polity":       ["Constitution", "Parliament & Legislature", "Judiciary", "Executive", "Federalism & Local Governance", "Rights & Duties", "Governance & Policy"],
    "Economy":      ["Planning & Growth", "Banking & Finance", "Fiscal Policy", "Agriculture Economy", "Trade & External Sector", "Infrastructure", "Social Sector"],
    "Environment":  ["Ecology & Ecosystems", "Biodiversity", "Climate Change", "Environmental Laws & Policy", "Protected Areas"],
    "Science & Technology": ["Physics & Chemistry", "Biology & Biotechnology", "Space & Defence", "IT & Digital", "Health & Disease"],
    "International Relations": ["Bilateral Relations", "International Organisations", "Treaties & Agreements", "Global Issues"],
    "Current Affairs": ["Miscellaneous"],
}

TOPIC_LIST = "\n".join(
    f"- {topic}: {', '.join(subs)}" for topic, subs in TOPICS.items()
)


def classify(q: dict) -> tuple[str, str]:
    prompt = f"""Classify this UPSC question into the most specific topic and subtopic.

Question: {q['question'][:300]}

Options:
{TOPIC_LIST}

Respond in EXACTLY this format (one line each):
TOPIC: <exact topic name>
SUBTOPIC: <exact subtopic name>"""

    resp = client.messages.create(
        model=MODEL, max_tokens=60, temperature=0,
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "TOPIC:"}
        ]
    )
    text = ("TOPIC:" + resp.content[0].text).strip()
    topic_m   = re.search(r'TOPIC:\s*(.+)', text)
    sub_m     = re.search(r'SUBTOPIC:\s*(.+)', text)
    topic     = topic_m.group(1).strip() if topic_m else "Current Affairs"
    subtopic  = sub_m.group(1).strip()   if sub_m   else "Miscellaneous"

    # Validate against known topics
    if topic not in TOPICS:
        # fuzzy match
        topic = min(TOPICS.keys(), key=lambda t: abs(len(t)-len(topic)))
    valid_subs = TOPICS.get(topic, [])
    if subtopic not in valid_subs and valid_subs:
        subtopic = valid_subs[0]

    return topic, subtopic


# ── Parse args ─────────────────────────────────────────────────────────────────
years = [2024, 2025]
if "--year" in sys.argv:
    idx = sys.argv.index("--year")
    years = [int(sys.argv[idx + 1])]

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

for year in years:
    rows = conn.execute(
        "SELECT * FROM questions WHERE year_first=? AND topic='Current Affairs' ORDER BY q_num",
        [year]
    ).fetchall()
    qs = [dict(r) for r in rows]

    print(f"\n{'='*55}")
    print(f"Reclassifying {year} — {len(qs)} questions tagged Current Affairs")
    print(f"{'='*55}")

    done = skipped = 0
    for i, q in enumerate(qs, 1):
        print(f"  [{i}/{len(qs)}] Q{q['q_num']} ...", end=" ", flush=True)
        topic, subtopic = classify(q)
        conn.execute(
            "UPDATE questions SET topic=?, subtopic=? WHERE id=?",
            [topic, subtopic, q["id"]]
        )
        conn.commit()
        print(f"{topic} > {subtopic}")
        done += 1
        if i < len(qs):
            time.sleep(DELAY_SEC)

    print(f"\n  Done: {done} reclassified")

conn.close()

print("\nReclassification complete. Restart the backend to pick up changes.")
