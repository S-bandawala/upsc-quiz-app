"""
UPSC Quiz App — FastAPI Backend
Endpoints:
  GET  /questions              → list questions (filter by topic, difficulty, year)
  GET  /questions/{id}         → single question (no answer leaked)
  POST /attempt                → submit answer → returns result + AI insight
  GET  /stats                  → overall + topic-wise performance
  GET  /topics                 → list all topics
  GET  /random                 → random question for quick practice
  GET  /repeated               → questions that appeared multiple years
"""

import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from groq import Groq
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Load .env ─────────────────────────────────────────────────────────────────
_ENV = Path(__file__).resolve().parent.parent / ".env"
if _ENV.exists():
    for _line in _ENV.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR.parent / "data" / "upsc_beta.db"

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

# Tavily API key (optional — falls back to DuckDuckGo snippets)
TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")


# ── DB Helper ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("year_tags", "source_pdfs"):
        if isinstance(d.get(field), str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
    return d


# ── FastAPI App ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DB_PATH.exists():
        raise RuntimeError(f"Database not found at {DB_PATH}. Run classify_and_build_db.py first.")
    # Add ai_explanation column if DB was created before this feature
    conn = get_db()
    try:
        conn.execute("ALTER TABLE questions ADD COLUMN ai_explanation TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.close()
    yield

app = FastAPI(title="UPSC Quiz API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────────────────────────────────────

class AttemptRequest(BaseModel):
    question_id: int
    selected_option: str       # a/b/c/d
    time_taken_sec: int = 0


class AttemptResponse(BaseModel):
    is_correct: bool
    correct_option: str | None
    ai_insight: str
    question_id: int


# ── Web Search ─────────────────────────────────────────────────────────────────

async def web_search(query: str) -> str:
    """Search for UPSC patterns. Uses Tavily if key set, else DuckDuckGo."""
    if TAVILY_KEY:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_KEY, "query": query,
                      "max_results": 3, "search_depth": "basic"}
            )
            if resp.status_code == 200:
                data = resp.json()
                snippets = [r.get("content", "") for r in data.get("results", [])[:3]]
                return "\n\n".join(snippets)

    # Fallback: DuckDuckGo Instant Answer API
    async with httpx.AsyncClient(timeout=8) as http:
        try:
            resp = await http.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            )
            data = resp.json()
            abstract = data.get("AbstractText", "")
            related = " | ".join(r.get("Text", "") for r in data.get("RelatedTopics", [])[:3])
            return (abstract + " " + related).strip() or "No web context found."
        except Exception:
            return "Web search unavailable."


async def generate_insight(question: dict, selected: str, web_ctx: str) -> str:
    """Use Claude to generate explanation + trap analysis."""
    correct = question.get("correct_option", "?")
    is_correct = selected.lower() == (correct or "").lower()

    prompt = f"""You are a UPSC expert mentor. A student just attempted this question:

QUESTION: {question['question']}
(a) {question.get('option_a','')}
(b) {question.get('option_b','')}
(c) {question.get('option_c','')}
(d) {question.get('option_d','')}

Student chose: ({selected}) | Correct answer: ({correct})
Result: {'CORRECT ✓' if is_correct else 'WRONG ✗'}

Topic: {question.get('topic','')} > {question.get('subtopic','')}
This question appeared in UPSC years: {question.get('year_tags', [])}
{"It has appeared " + str(question.get('frequency',1)) + " times — HIGH PRIORITY!" if question.get('frequency',1) > 1 else ""}

Web context about this topic:
{web_ctx[:1500]}

Write a concise insight (4-6 lines) covering:
1. Why the correct answer is right (core fact/logic)
2. Why the wrong options are traps (if student got it wrong — explain their mistake)
3. UPSC pattern: what this question tests and how UPSC usually frames it
4. Memory tip: one-line mnemonic or trick to never forget this

Be direct. No fluff. Use plain English.
"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=600,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/topics")
def get_topics():
    conn = get_db()
    rows = conn.execute("""
        SELECT parent_topic as topic, name as subtopic, COUNT(q.id) as q_count
        FROM topics t
        LEFT JOIN questions q ON q.subtopic = t.name
        GROUP BY t.parent_topic, t.name
        ORDER BY t.parent_topic, t.name
    """).fetchall()
    conn.close()

    result = {}
    for r in rows:
        topic = r["topic"]
        if topic not in result:
            result[topic] = []
        result[topic].append({"subtopic": r["subtopic"], "count": r["q_count"]})

    return result


@app.get("/questions")
def list_questions(
    topic: Optional[str] = Query(None),
    topics: Optional[str] = Query(None),
    subtopic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    repeated_only: bool = Query(False),
    limit: int = Query(20, le=500),
    offset: int = Query(0),
):
    conn = get_db()
    filters = []
    params: list = []

    if topics:
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        if topic_list:
            placeholders = ",".join("?" * len(topic_list))
            filters.append(f"topic IN ({placeholders})")
            params.extend(topic_list)
    elif topic:
        filters.append("topic = ?")
        params.append(topic)
    if subtopic:
        filters.append("subtopic = ?")
        params.append(subtopic)
    if difficulty:
        filters.append("difficulty = ?")
        params.append(difficulty)
    if year:
        filters.append("year_tags LIKE ?")
        params.append(f'%{year}%')
    if repeated_only:
        filters.append("is_repeated = 1")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    rows = conn.execute(
        f"SELECT * FROM questions {where} ORDER BY frequency DESC, year_first DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    total = conn.execute(f"SELECT COUNT(*) FROM questions {where}", params).fetchone()[0]
    conn.close()

    # Don't leak correct_option in list view
    questions = []
    for r in rows:
        d = row_to_dict(r)
        d.pop("correct_option", None)
        questions.append(d)

    return {"total": total, "offset": offset, "questions": questions}


@app.get("/questions/random")
def get_random(
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
):
    conn = get_db()
    filters = []
    params: list = []
    if topic:
        filters.append("topic = ?")
        params.append(topic)
    if difficulty:
        filters.append("difficulty = ?")
        params.append(difficulty)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    row = conn.execute(
        f"SELECT * FROM questions {where} ORDER BY RANDOM() LIMIT 1", params
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "No questions found")

    d = row_to_dict(row)
    d.pop("correct_option", None)
    return d


@app.get("/questions/repeated")
def get_repeated(limit: int = Query(50)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM questions WHERE is_repeated = 1 ORDER BY frequency DESC LIMIT ?",
        [limit]
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = row_to_dict(r)
        d.pop("correct_option", None)
        result.append(d)
    return {"count": len(result), "questions": result}


@app.get("/questions/{question_id}")
def get_question(question_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", [question_id]).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Question not found")
    d = row_to_dict(row)
    d.pop("correct_option", None)
    return d


@app.post("/attempt", response_model=AttemptResponse)
async def submit_attempt(body: AttemptRequest):
    conn = get_db()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", [body.question_id]).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Question not found")

    q = row_to_dict(row)
    correct = q.get("correct_option")
    selected = body.selected_option.lower().strip()
    is_correct = selected == (correct or "").lower()

    # Use cached explanation if available, else generate + cache it
    insight = q.get("ai_explanation")
    if not insight:
        search_query = f"UPSC {q.get('topic','')} {q['question'][:100]} explanation"
        web_ctx = await web_search(search_query)
        insight = await generate_insight(q, selected, web_ctx)
        # Cache explanation permanently on the question row
        conn.execute(
            "UPDATE questions SET ai_explanation = ? WHERE id = ?",
            [insight, body.question_id]
        )

    # Save attempt
    conn.execute("""
        INSERT INTO attempts (question_id, selected_option, is_correct, time_taken_sec, ai_insight)
        VALUES (?, ?, ?, ?, ?)
    """, [body.question_id, selected, int(is_correct), body.time_taken_sec, insight])

    # Update topic stats
    conn.execute("""
        INSERT INTO topic_stats (topic, subtopic, total_attempted, total_correct, avg_time_sec)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT DO NOTHING
    """, [q.get("topic"), q.get("subtopic"), int(is_correct), body.time_taken_sec])

    conn.execute("""
        UPDATE topic_stats
        SET total_attempted = total_attempted + 1,
            total_correct = total_correct + ?,
            avg_time_sec = (avg_time_sec * (total_attempted - 1) + ?) / total_attempted
        WHERE topic = ? AND subtopic = ?
    """, [int(is_correct), body.time_taken_sec, q.get("topic"), q.get("subtopic")])

    conn.commit()
    conn.close()

    return AttemptResponse(
        is_correct=is_correct,
        correct_option=correct,
        ai_insight=insight,
        question_id=body.question_id,
    )


@app.get("/stats")
def get_stats():
    conn = get_db()

    overall = conn.execute("""
        SELECT
            COUNT(*) as total_attempted,
            SUM(is_correct) as total_correct,
            ROUND(AVG(is_correct)*100, 1) as accuracy_pct,
            ROUND(AVG(time_taken_sec), 1) as avg_time_sec
        FROM attempts
    """).fetchone()

    topic_stats = conn.execute("""
        SELECT topic, subtopic, total_attempted, total_correct,
               ROUND(CAST(total_correct AS REAL)/NULLIF(total_attempted,0)*100, 1) as accuracy_pct,
               avg_time_sec
        FROM topic_stats
        ORDER BY accuracy_pct ASC
    """).fetchall()

    db_stats = conn.execute("""
        SELECT topic, COUNT(*) as q_count,
               SUM(is_repeated) as repeated_count,
               ROUND(AVG(frequency), 1) as avg_frequency
        FROM questions
        GROUP BY topic ORDER BY q_count DESC
    """).fetchall()

    conn.close()

    return {
        "overall": dict(overall) if overall else {},
        "by_topic_performance": [dict(r) for r in topic_stats],
        "db_summary": [dict(r) for r in db_stats],
    }


@app.get("/health")
def health():
    conn = get_db()
    q_count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    conn.close()
    return {"status": "ok", "questions_in_db": q_count}


# ── Serve Frontend ────────────────────────────────────────────────────────────
FRONTEND_DIR = BASE_DIR.parent / "frontend"

@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")

# Mount static files (CSS, JS, images if any) — must be after all API routes
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
