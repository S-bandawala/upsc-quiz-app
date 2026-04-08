# UPSC CSE Prelims Quiz App

A full-stack question bank and practice platform for UPSC Civil Services Preliminary Examination (GS Paper-I).

## What it does

- **827 verified questions** across 9 years (2015–2023)
- **Set A answers** verified from official UPSC answer keys
- **AI-powered explanations** — get detailed analysis, traps, and logic for every question
- **Practice Mode** — filter by topic, year, difficulty; choose how many questions to attempt
- **Mock Tests** — timed tests with full review, score breakdown, and AI mentor analysis
- **Stats Dashboard** — track your accuracy, topic-wise performance, and progress
- **Study Calendar** — plan your preparation schedule
- **Dark/Light theme** toggle

## Screenshots

> Coming soon

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React (CDN) + Custom CSS |
| Backend | Python FastAPI |
| Database | SQLite |
| AI Explanations | Groq API (Llama 3.3 — free tier) |
| PDF Extraction | Groq Vision AI (Llama 4 Scout — free tier) |
| PDF Rendering | PyMuPDF (fitz) |

**Total cost: $0** — built entirely on free-tier APIs.

## Question Bank Stats

| Year | Questions | Answers Verified |
|------|-----------|-----------------|
| 2015 | 95 | Yes (Set A) |
| 2016 | 99 | No answer key |
| 2017 | 93 | Yes (Set A) |
| 2018 | 93 | Yes (Set A) |
| 2019 | 96 | Yes (Set A) |
| 2020 | 83 | Yes (Set A) |
| 2021 | 95 | Yes (Set A) |
| 2022 | 86 | Yes (Set A) |
| 2023 | 87 | Yes (Set A) |

Topics covered: Polity, Economy, History, Environment, Science & Technology, Geography, International Relations, Current Affairs.

## How to run locally

### 1. Clone the repo
```bash
git clone https://github.com/S-bandawala/upsc-quiz-app.git
cd upsc-quiz-app
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up API key (for AI explanations)
Create a `.env` file in the root folder:
```
GROQ_API_KEY=your_groq_api_key_here
```
Get a free key at [console.groq.com](https://console.groq.com)

### 4. Start the app
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Open **http://localhost:8000** in your browser.

## Project Structure

```
upsc-quiz-app/
├── backend/
│   └── main.py              # FastAPI server + API endpoints
├── frontend/
│   └── index.html           # React SPA (single file)
├── data/
│   ├── upsc_beta.db         # SQLite database (827 questions)
│   ├── beta_questions.json  # Classified question bank
│   ├── flagged_questions.json # Questions pending re-extraction
│   └── cache/               # Per-year extraction cache
├── scripts/
│   ├── extract_questions.py # Groq Vision PDF extractor
│   ├── rebuild_db.py        # Rebuild DB from JSON (no API needed)
│   └── ...                  # Other utility scripts
├── requirements.txt
├── Procfile                 # For cloud deployment
└── .env.example             # API key template
```

## How questions were extracted

1. UPSC question papers (image-based PDFs) rendered page by page using PyMuPDF
2. Each page sent to Groq Vision AI (Llama 4 Scout) for OCR + structured extraction
3. Answer keys extracted from page 1 only (Set A) of official UPSC answer key PDFs
4. Questions classified into UPSC syllabus topics using Groq text model (Llama 3.3)
5. All data cached per-year to avoid re-extraction

## Upcoming

- 2024 and 2025 question extraction
- Re-extraction of 41 flagged questions with improved prompts
- Deployment to free hosting (Render / Fly.io)
- WhatsApp daily challenge feature
- Bookmarks and notes

## License

This project is for educational purposes. UPSC question papers are publicly available documents.

---

Built with Python, FastAPI, React, and Groq AI.
