"""
Classify NEW questions only (not already in beta_questions.json) and rebuild DB.
Uses Groq text model — separate quota from vision model.
"""

import json
import os
import re
import sqlite3
import time
from pathlib import Path

from groq import Groq

# ── Load .env ──
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "upsc_beta.db"
RAW_JSON = DATA_DIR / "raw_questions.json"
BETA_JSON = DATA_DIR / "beta_questions.json"

client = Groq(api_key=os.environ["GROQ_API_KEY"])
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

VALID_TOPICS = [
    "History", "Geography", "Polity", "Economy",
    "Environment", "Science & Technology",
    "International Relations", "Current Affairs"
]

TOPICS_DB = {
    "History": ["Ancient India", "Medieval India", "Modern India", "Indian Art & Culture", "Post-Independence India"],
    "Geography": ["Physical Geography", "Indian Geography", "World Geography", "Climate & Monsoon"],
    "Polity": ["Constitution", "Parliament & Legislature", "Judiciary", "Governance & Policy"],
    "Economy": ["Planning & Growth", "Banking & Finance", "Fiscal Policy", "Trade & External Sector"],
    "Environment": ["Ecology & Ecosystems", "Biodiversity", "Climate Change", "Environmental Laws & Policy"],
    "Science & Technology": ["Space Technology", "Defence Technology", "Biotechnology", "Health & Medicine"],
    "International Relations": ["India & Neighbours", "India & World", "International Organizations"],
    "Current Affairs": ["National Events", "International Events"],
}

CLASSIFY_PROMPT = """Classify these UPSC questions by topic.

Valid topics: History, Geography, Polity, Economy, Environment, Science & Technology, International Relations, Current Affairs

For each question, return JSON array:
[{"id": 1, "topic": "...", "subtopic": "...", "difficulty": "easy|medium|hard"}, ...]

Questions:
{questions}

Return ONLY the JSON array, no markdown."""


def classify_batch(questions):
    q_text = "\n".join(
        f"ID {q['id']}: {q['question'][:200]}" for q in questions
    )
    prompt = CLASSIFY_PROMPT.replace("{questions}", q_text)

    max_retries = 10
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1
            )
            raw = resp.choices[0].message.content.strip()
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            if m:
                results = json.loads(m.group())
                for r in results:
                    if r.get("topic") not in VALID_TOPICS:
                        r["topic"] = "Current Affairs"
                return results
            return []
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait = 30
                m2 = re.search(r'try again in ([\d.]+)s', str(e))
                if m2:
                    wait = float(m2.group(1)) + 5
                print(f"    Rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"    Error: {e}")
                return []
    return []


def compute_frequency(questions):
    """Deduplicate and compute frequency across years."""
    from difflib import SequenceMatcher
    unique = []
    seen = set()

    for q in questions:
        text = q["question"].strip().lower()[:100]
        if text in seen:
            # Find matching unique question and update
            for u in unique:
                if u["question"].strip().lower()[:100] == text:
                    if q["year"] not in u["year_tags"]:
                        u["year_tags"].append(q["year"])
                        u["frequency"] += 1
                    break
            continue
        seen.add(text)
        unique.append({
            **q,
            "year_first": q["year"],
            "year_tags": [q["year"]],
            "frequency": 1,
            "is_repeated": 0,
            "source_pdfs": [q.get("source_pdf", "")],
        })

    for u in unique:
        u["is_repeated"] = 1 if u["frequency"] > 1 else 0

    return unique


def main():
    print("=" * 60)
    print("Classify NEW questions + Rebuild DB")
    print("=" * 60)

    # Load existing classified questions
    existing = {}
    if BETA_JSON.exists():
        old_beta = json.loads(BETA_JSON.read_text(encoding="utf-8"))
        for q in old_beta:
            key = q["question"].strip().lower()[:100]
            existing[key] = q
        print(f"Existing classified: {len(existing)} questions")

    # Load all raw questions
    with open(RAW_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    print(f"Total raw questions: {len(raw)}")

    # Deduplicate
    all_unique = compute_frequency(raw)
    print(f"Unique questions: {len(all_unique)}")

    # Split into already-classified and new
    new_qs = []
    classified_qs = []
    for q in all_unique:
        key = q["question"].strip().lower()[:100]
        if key in existing:
            old = existing[key]
            # Keep old classification but update answer from new data
            old["correct_option"] = q.get("correct_option") or old.get("correct_option")
            old["q_num"] = q.get("q_num") or old.get("q_num")
            old["year_tags"] = q.get("year_tags", old.get("year_tags", []))
            old["frequency"] = q.get("frequency", old.get("frequency", 1))
            old["is_repeated"] = q.get("is_repeated", old.get("is_repeated", 0))
            classified_qs.append(old)
        else:
            new_qs.append(q)

    print(f"Already classified: {len(classified_qs)}")
    print(f"Need classification: {len(new_qs)}")

    # Classify new questions in batches
    if new_qs:
        print(f"\nClassifying {len(new_qs)} new questions...")
        BATCH_SIZE = 20
        classifications = {}

        for i, q in enumerate(new_qs, 1):
            q["id"] = 10000 + i  # temp IDs

        for start in range(0, len(new_qs), BATCH_SIZE):
            batch = new_qs[start:start + BATCH_SIZE]
            batch_num = start // BATCH_SIZE + 1
            total_batches = -(-len(new_qs) // BATCH_SIZE)
            print(f"  Batch {batch_num}/{total_batches}...", end=" ", flush=True)

            results = classify_batch(batch)
            for r in results:
                classifications[r["id"]] = r
            print(f"OK ({len(results)} classified)")
            time.sleep(0.5)

        for q in new_qs:
            clf = classifications.get(q["id"], {})
            q["topic"] = clf.get("topic", "Current Affairs")
            q["subtopic"] = clf.get("subtopic", "")
            q["difficulty"] = clf.get("difficulty", "medium")

    # Merge all
    all_qs = classified_qs + new_qs
    all_qs.sort(key=lambda x: (-x.get("frequency", 1), -x.get("year_first", 0)))

    # Assign final IDs
    for i, q in enumerate(all_qs, 1):
        q["id"] = i

    # Save beta_questions.json
    with open(BETA_JSON, "w", encoding="utf-8") as f:
        json.dump(all_qs, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_qs)} questions to beta_questions.json")

    # Rebuild DB
    print(f"\nRebuilding database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    DROP TABLE IF EXISTS questions;
    DROP TABLE IF EXISTS topics;
    DROP TABLE IF EXISTS topic_stats;
    """)

    conn.execute("""CREATE TABLE topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, paper TEXT DEFAULT 'GS1', parent_topic TEXT)""")

    conn.execute("""CREATE TABLE questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL, option_a TEXT, option_b TEXT, option_c TEXT, option_d TEXT,
        correct_option TEXT, topic TEXT, subtopic TEXT, difficulty TEXT DEFAULT 'medium',
        year_first INTEGER, year_tags TEXT, frequency INTEGER DEFAULT 1,
        source_pdfs TEXT, paper TEXT DEFAULT 'GS1', q_num INTEGER,
        is_repeated INTEGER DEFAULT 0, ai_explanation TEXT)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER REFERENCES questions(id),
        selected_option TEXT, is_correct INTEGER, time_taken_sec INTEGER,
        ai_insight TEXT, attempted_at TEXT DEFAULT (datetime('now')))""")

    conn.execute("""CREATE TABLE topic_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT, subtopic TEXT, total_attempted INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0, avg_time_sec REAL DEFAULT 0)""")

    conn.execute("CREATE INDEX idx_q_topic ON questions(topic)")
    conn.execute("CREATE INDEX idx_q_year ON questions(year_first)")

    for topic, subs in TOPICS_DB.items():
        for s in subs:
            conn.execute("INSERT INTO topics (name, paper, parent_topic) VALUES (?, 'GS1', ?)", (s, topic))

    inserted = 0
    with_answer = 0
    for q in all_qs:
        if q.get("correct_option"):
            with_answer += 1
        conn.execute("""
            INSERT INTO questions (question, option_a, option_b, option_c, option_d,
                correct_option, topic, subtopic, difficulty, year_first, year_tags,
                frequency, source_pdfs, paper, q_num, is_repeated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'GS1',?,?)
        """, (
            q["question"], q.get("option_a"), q.get("option_b"),
            q.get("option_c"), q.get("option_d"), q.get("correct_option"),
            q.get("topic", "Current Affairs"), q.get("subtopic", ""),
            q.get("difficulty", "medium"), q.get("year_first"),
            json.dumps(q.get("year_tags", [])), q.get("frequency", 1),
            json.dumps(q.get("source_pdfs", [])), q.get("q_num"),
            q.get("is_repeated", 0),
        ))
        inserted += 1

    conn.commit()
    conn.close()

    print(f"\nDatabase rebuilt: {DB_PATH}")
    print(f"Questions: {inserted}")
    print(f"With answers: {with_answer}")

    from collections import Counter
    tc = Counter(q.get("topic", "?") for q in all_qs)
    print("\nTopic breakdown:")
    for t, c in tc.most_common():
        print(f"  {t:30s} {c:3d}")

    yc = Counter(q.get("year_first") for q in all_qs)
    print("\nYear breakdown:")
    for y, c in sorted(yc.items()):
        print(f"  {y}: {c}")


if __name__ == "__main__":
    main()
