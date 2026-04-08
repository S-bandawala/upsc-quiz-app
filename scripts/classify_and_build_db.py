"""
UPSC Question Classifier + DB Builder
- Reads raw_questions.json
- Classifies each question by UPSC syllabus topic via Ollama (free, local)
- Computes year_tags (all years it appeared) and frequency (times appeared)
- Builds SQLite database: upsc_beta.db
- Beta: first 250 GS-1 questions
"""

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from difflib import SequenceMatcher
from groq import Groq

# ── Load .env ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
_ENV = BASE_DIR / ".env"
if _ENV.exists():
    for _line in _ENV.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip()

# ── Config ─────────────────────────────────────────────────────────────────────
DATA_DIR = BASE_DIR / "data"
RAW_JSON = DATA_DIR / "raw_questions.json"
DB_PATH = DATA_DIR / "upsc_beta.db"

client = Groq(api_key=os.environ["GROQ_API_KEY"])
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

# ── UPSC GS-1 Syllabus Topics ──────────────────────────────────────────────────
TOPICS = {
    "History": [
        "Ancient India", "Medieval India", "Modern India",
        "Indian Art & Culture", "Post-Independence India"
    ],
    "Geography": [
        "Physical Geography", "Indian Geography", "World Geography",
        "Climate & Monsoon", "Rivers & Water Bodies", "Resources & Agriculture"
    ],
    "Polity": [
        "Constitution", "Parliament & Legislature", "Judiciary",
        "Executive", "Federalism & Local Governance",
        "Rights & Duties", "Governance & Policy"
    ],
    "Economy": [
        "Planning & Growth", "Banking & Finance", "Fiscal Policy",
        "Agriculture Economy", "Trade & External Sector",
        "Infrastructure", "Social Sector"
    ],
    "Environment": [
        "Ecology & Ecosystems", "Biodiversity", "Climate Change",
        "Environmental Laws & Policy", "Protected Areas"
    ],
    "Science & Technology": [
        "Space Technology", "Defence Technology", "Biotechnology",
        "IT & Digital", "Health & Medicine", "Everyday Science"
    ],
    "International Relations": [
        "India & Neighbours", "India & World", "International Organizations",
        "Treaties & Agreements"
    ],
    "Current Affairs": [
        "National Events", "International Events",
        "Awards & Recognition", "Reports & Indices"
    ],
}

TOPIC_LIST_STR = "\n".join(
    f"- {topic}: {', '.join(subs)}"
    for topic, subs in TOPICS.items()
)


# ── Similarity for dedup ───────────────────────────────────────────────────────

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_similar_question(question_text: str, existing: list[dict], threshold=0.80) -> int | None:
    """Return id of an existing similar question, or None."""
    for eq in existing:
        if similarity(question_text, eq["question"]) >= threshold:
            return eq["id"]
    return None


# ── Classify questions via Claude ──────────────────────────────────────────────

CLASSIFY_PROMPT = """You are a UPSC expert. Classify each question into the correct topic and subtopic.

Available topics and subtopics:
{topics}

Questions to classify (JSON array):
{questions}

Return a JSON array with exactly one object per question in the same order:
[
  {{"id": <id>, "topic": "<topic>", "subtopic": "<subtopic>", "difficulty": "<easy|medium|hard>"}},
  ...
]

Rules:
- topic must be exactly one of the topic names listed
- subtopic must be one of that topic's subtopics
- difficulty: easy (direct fact), medium (application), hard (multi-step reasoning)
- Return ONLY valid JSON, no explanation
"""


def classify_batch(questions: list[dict]) -> list[dict]:
    """Classify a batch of questions using Groq (free)."""
    q_payload = [{"id": q["id"], "question": q["question"][:300]} for q in questions]

    prompt = CLASSIFY_PROMPT.format(
        topics=TOPIC_LIST_STR,
        questions=json.dumps(q_payload, ensure_ascii=False)
    )

    max_retries = 10
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=GROQ_TEXT_MODEL,
                max_tokens=3000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.choices[0].message.content.strip()

            json_match = re.search(r'\[.+\]', raw, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            return []
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
                print(f"\n    Rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})...", end="", flush=True)
                time.sleep(wait)
            else:
                raise
    return []


# ── Database Setup ─────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        paper TEXT DEFAULT 'GS1',
        parent_topic TEXT
    );

    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        correct_option TEXT,          -- a/b/c/d or NULL if unknown
        topic TEXT,
        subtopic TEXT,
        difficulty TEXT DEFAULT 'medium',
        year_first INTEGER,           -- first year this Q appeared
        year_tags TEXT,               -- JSON array of all years: [2019, 2022]
        frequency INTEGER DEFAULT 1,  -- times appeared across years
        source_pdfs TEXT,             -- JSON array of source file names
        paper TEXT DEFAULT 'GS1',
        q_num INTEGER,                 -- original question number (1-100) from UPSC paper
        is_repeated INTEGER DEFAULT 0, -- 1 if appeared in multiple years
        ai_explanation TEXT            -- cached AI insight (generated on first attempt)
    );

    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER REFERENCES questions(id),
        selected_option TEXT,
        is_correct INTEGER,
        time_taken_sec INTEGER,
        ai_insight TEXT,
        attempted_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS topic_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        subtopic TEXT,
        total_attempted INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        avg_time_sec REAL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_q_topic ON questions(topic);
    CREATE INDEX IF NOT EXISTS idx_q_year ON questions(year_first);
    CREATE INDEX IF NOT EXISTS idx_q_difficulty ON questions(difficulty);
    CREATE INDEX IF NOT EXISTS idx_q_frequency ON questions(frequency);
    """)
    conn.commit()


def seed_topics(conn: sqlite3.Connection):
    conn.execute("DELETE FROM topics")
    for topic, subtopics in TOPICS.items():
        for sub in subtopics:
            conn.execute(
                "INSERT INTO topics (name, paper, parent_topic) VALUES (?, 'GS1', ?)",
                (sub, topic)
            )
    conn.commit()


# ── Frequency / Year-tag computation ──────────────────────────────────────────

def compute_frequency(questions: list[dict]) -> list[dict]:
    """
    Group similar questions across years.
    Assigns: year_tags, frequency, is_repeated, year_first.
    """
    groups: list[dict] = []  # {canonical_q, year_tags, source_pdfs, all_data}

    for q in questions:
        matched = False
        for g in groups:
            if similarity(q["question"], g["canonical_q"]) >= 0.80:
                if q["year"] not in g["year_tags"]:
                    g["year_tags"].append(q["year"])
                g["source_pdfs"].append(q["source_pdf"])
                # Prefer entry with answer
                if not g["best"].get("correct_option") and q.get("correct_option"):
                    g["best"] = q
                matched = True
                break
        if not matched:
            groups.append({
                "canonical_q": q["question"],
                "year_tags": [q["year"]],
                "source_pdfs": [q["source_pdf"]],
                "best": q,
            })

    enriched = []
    for g in groups:
        q = dict(g["best"])
        q["year_tags"] = sorted(g["year_tags"])
        q["year_first"] = min(g["year_tags"])
        q["frequency"] = len(g["year_tags"])
        q["is_repeated"] = 1 if q["frequency"] > 1 else 0
        q["source_pdfs"] = list(set(g["source_pdfs"]))
        enriched.append(q)

    return enriched


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("UPSC Classifier + DB Builder")
    print("=" * 60)

    # Load raw questions
    if not RAW_JSON.exists():
        print(f"ERROR: {RAW_JSON} not found. Run extract_questions.py first.")
        return

    with open(RAW_JSON, encoding="utf-8") as f:
        raw_questions = json.load(f)

    print(f"Loaded {len(raw_questions)} raw questions")

    # Compute frequency / dedup across years
    print("\nComputing frequency and deduplicating similar questions...")
    enriched = compute_frequency(raw_questions)
    print(f"Unique questions after dedup: {len(enriched)}")

    # Sort by frequency desc, then year desc — most repeated & recent first
    enriched.sort(key=lambda x: (-x["frequency"], -x["year_first"]))

    # Take all unique questions (no beta limit)
    beta_qs = enriched
    print(f"\nBeta set: {len(beta_qs)} questions")
    print(f"  Repeated questions: {sum(1 for q in beta_qs if q['is_repeated'])}")
    print(f"  Single-year questions: {sum(1 for q in beta_qs if not q['is_repeated'])}")

    # Assign temp IDs for classification
    for i, q in enumerate(beta_qs, 1):
        q["id"] = i

    # Classify in batches of 20
    print("\nClassifying questions by UPSC syllabus topic...")
    BATCH_SIZE = 20
    classifications = {}

    for start in range(0, len(beta_qs), BATCH_SIZE):
        batch = beta_qs[start:start + BATCH_SIZE]
        print(f"  Classifying batch {start//BATCH_SIZE + 1}/{-(-len(beta_qs)//BATCH_SIZE)}...", end=" ")
        try:
            results = classify_batch(batch)
            for r in results:
                classifications[r["id"]] = r
            print(f"OK ({len(results)} classified)")
        except Exception as e:
            print(f"FAILED: {e}")
        time.sleep(0.5)  # rate limit courtesy

    # Apply classifications
    for q in beta_qs:
        clf = classifications.get(q["id"], {})
        q["topic"] = clf.get("topic", "Current Affairs")
        q["subtopic"] = clf.get("subtopic", "")
        q["difficulty"] = clf.get("difficulty", "medium")

    # Save enriched beta set
    beta_json = DATA_DIR / "beta_questions.json"
    with open(beta_json, "w", encoding="utf-8") as f:
        json.dump(beta_qs, f, ensure_ascii=False, indent=2)
    print(f"\nSaved beta questions >> {beta_json}")

    # Build SQLite DB
    print(f"\nBuilding database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    seed_topics(conn)

    inserted = 0
    for q in beta_qs:
        conn.execute("""
            INSERT INTO questions (
                question, option_a, option_b, option_c, option_d,
                correct_option, topic, subtopic, difficulty,
                year_first, year_tags, frequency, source_pdfs,
                paper, q_num, is_repeated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GS1', ?, ?)
        """, (
            q["question"],
            q.get("option_a"), q.get("option_b"),
            q.get("option_c"), q.get("option_d"),
            q.get("correct_option"),
            q["topic"], q["subtopic"], q["difficulty"],
            q["year_first"],
            json.dumps(q["year_tags"]),
            q["frequency"],
            json.dumps(q["source_pdfs"]),
            q.get("q_num"),
            q["is_repeated"],
        ))
        inserted += 1

    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"Database built: {DB_PATH}")
    print(f"Questions inserted: {inserted}")

    # Print topic breakdown
    print("\nTopic breakdown:")
    from collections import Counter
    topic_counts = Counter(q["topic"] for q in beta_qs)
    for topic, count in topic_counts.most_common():
        print(f"  {topic:30s} {count:3d} Qs")

    print("\nNext step: run the backend with: cd backend && uvicorn main:app --reload")


if __name__ == "__main__":
    main()
