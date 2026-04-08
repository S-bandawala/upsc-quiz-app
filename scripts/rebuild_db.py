"""
Rebuild SQLite DB from beta_questions.json (already classified + corrected answers).
No API calls needed — just loads JSON and inserts into DB.
"""

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "upsc_beta.db"
BETA_JSON = DATA_DIR / "beta_questions.json"

TOPICS = {
    "History": ["Ancient India", "Medieval India", "Modern India", "Indian Art & Culture", "Post-Independence India"],
    "Geography": ["Physical Geography", "Indian Geography", "World Geography", "Climate & Monsoon", "Rivers & Water Bodies", "Resources & Agriculture"],
    "Polity": ["Constitution", "Parliament & Legislature", "Judiciary", "Executive", "Federalism & Local Governance", "Rights & Duties", "Governance & Policy"],
    "Economy": ["Planning & Growth", "Banking & Finance", "Fiscal Policy", "Agriculture Economy", "Trade & External Sector", "Infrastructure", "Social Sector"],
    "Environment": ["Ecology & Ecosystems", "Biodiversity", "Climate Change", "Environmental Laws & Policy", "Protected Areas"],
    "Science & Technology": ["Space Technology", "Defence Technology", "Biotechnology", "IT & Digital", "Health & Medicine", "Everyday Science"],
    "International Relations": ["India & Neighbours", "India & World", "International Organizations", "Treaties & Agreements"],
    "Current Affairs": ["National Events", "International Events", "Awards & Recognition", "Reports & Indices"],
}


def init_db(conn):
    conn.executescript("""
    DROP TABLE IF EXISTS questions;
    DROP TABLE IF EXISTS topics;
    DROP TABLE IF EXISTS topic_stats;

    CREATE TABLE topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        paper TEXT DEFAULT 'GS1',
        parent_topic TEXT
    );

    CREATE TABLE questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        correct_option TEXT,
        topic TEXT,
        subtopic TEXT,
        difficulty TEXT DEFAULT 'medium',
        year_first INTEGER,
        year_tags TEXT,
        frequency INTEGER DEFAULT 1,
        source_pdfs TEXT,
        paper TEXT DEFAULT 'GS1',
        q_num INTEGER,
        is_repeated INTEGER DEFAULT 0,
        ai_explanation TEXT
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

    CREATE TABLE topic_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        subtopic TEXT,
        total_attempted INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        avg_time_sec REAL DEFAULT 0
    );

    CREATE INDEX idx_q_topic ON questions(topic);
    CREATE INDEX idx_q_year ON questions(year_first);
    CREATE INDEX idx_q_difficulty ON questions(difficulty);
    CREATE INDEX idx_q_frequency ON questions(frequency);
    """)
    conn.commit()


def main():
    print("=" * 60)
    print("Rebuild DB from beta_questions.json (no API needed)")
    print("=" * 60)

    with open(BETA_JSON, encoding="utf-8") as f:
        beta_qs = json.load(f)

    print(f"Loaded {len(beta_qs)} questions from beta_questions.json")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Seed topics
    for topic, subtopics in TOPICS.items():
        for sub in subtopics:
            conn.execute("INSERT INTO topics (name, paper, parent_topic) VALUES (?, 'GS1', ?)", (sub, topic))

    # Insert questions
    inserted = 0
    with_answer = 0
    for q in beta_qs:
        correct = q.get("correct_option")
        if correct:
            with_answer += 1

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
            correct,
            q.get("topic", "Current Affairs"),
            q.get("subtopic", ""),
            q.get("difficulty", "medium"),
            q.get("year_first"),
            json.dumps(q.get("year_tags", [])),
            q.get("frequency", 1),
            json.dumps(q.get("source_pdfs", [])),
            q.get("q_num"),
            q.get("is_repeated", 0),
        ))
        inserted += 1

    conn.commit()
    conn.close()

    print(f"\nDatabase rebuilt: {DB_PATH}")
    print(f"Questions inserted: {inserted}")
    print(f"With correct answers: {with_answer}")

    # Topic breakdown
    from collections import Counter
    topic_counts = Counter(q.get("topic", "Unknown") for q in beta_qs)
    print("\nTopic breakdown:")
    for topic, count in topic_counts.most_common():
        print(f"  {topic:30s} {count:3d} Qs")

    year_counts = Counter(q.get("year_first") for q in beta_qs)
    print("\nYear breakdown:")
    for year, count in sorted(year_counts.items()):
        print(f"  {year}: {count} Qs")


if __name__ == "__main__":
    main()
