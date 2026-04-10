"""
Full DB update:
1. Normalize messy subtopic names → canonical subtopics
2. Fix blank subtopics
3. Rebuild topics table from scratch
4. Recompute frequency + is_repeated
5. Update topic_stats table structure

Usage: python scripts/update_db.py
"""

import sqlite3, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "upsc_beta.db"

# ── Canonical topic/subtopic map ──────────────────────────────────────────────
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
        "Physics & Chemistry", "Biology & Biotechnology",
        "Space & Defence", "IT & Digital", "Health & Disease"
    ],
    "International Relations": [
        "Bilateral Relations", "International Organisations",
        "Treaties & Agreements", "Global Issues"
    ],
    "Current Affairs": ["Miscellaneous"],
}

# ── Subtopic normalization map (messy → canonical) ────────────────────────────
NORMALIZE_SUB = {
    # Economy
    "Agriculture": "Agriculture Economy",
    "Banking": "Banking & Finance",
    "External Sector": "Trade & External Sector",
    "International Trade & External Sector": "Trade & External Sector",
    "Monetary Policy": "Banking & Finance",
    "Monetary policy": "Banking & Finance",
    "Inflation": "Fiscal Policy",
    "Inflation control": "Fiscal Policy",
    "Taxation": "Fiscal Policy",
    "International Financial Institutions": "Banking & Finance",
    "International Organizations": "Trade & External Sector",
    "Resources & Agriculture": "Agriculture Economy",
    "Black Money": "Fiscal Policy",
    "Central Bank Functions": "Banking & Finance",
    "Coal Controller's Organization": "Infrastructure",
    "Convertible Bonds": "Banking & Finance",
    "Credit rating agencies": "Banking & Finance",
    "Currency and Trade": "Trade & External Sector",
    "E-commerce and Trade": "Trade & External Sector",
    "Economic Recession": "Planning & Growth",
    "Exchange Rates": "Trade & External Sector",
    "Financial Management": "Banking & Finance",
    "Financial Markets": "Banking & Finance",
    "Government Bond Yields": "Fiscal Policy",
    "Government Borrowings": "Fiscal Policy",
    "Industrial disputes": "Social Sector",
    "Investments and Markets": "Banking & Finance",
    "Market Demand": "Planning & Growth",
    "Money Supply": "Banking & Finance",
    "Sectors of the Economy": "Planning & Growth",
    # Environment
    "Afforestation": "Ecology & Ecosystems",
    "Biodiversity and Conservation": "Biodiversity",
    "Biogeochemical Cycles": "Ecology & Ecosystems",
    "Carbon Sequestration": "Climate Change",
    "Climate Action": "Climate Change",
    "Ecosystems and Biomes": "Ecology & Ecosystems",
    "Electronic Waste": "Environmental Laws & Policy",
    "Environmental Issues": "Environmental Laws & Policy",
    "Environmental Laws": "Environmental Laws & Policy",
    "Forestry": "Ecology & Ecosystems",
    "Fungi": "Ecology & Ecosystems",
    "Greenhouse Gases": "Climate Change",
    "Nitrogen-fixing Plants": "Ecology & Ecosystems",
    "Pollution": "Environmental Laws & Policy",
    "Sustainable Agriculture": "Ecology & Ecosystems",
    "Sustainable Development": "Environmental Laws & Policy",
    "Water Conservation": "Ecology & Ecosystems",
    "Water and Sanitation": "Ecology & Ecosystems",
    "Wetlands": "Biodiversity",
    "Wildlife": "Biodiversity",
    "Wildlife Conservation": "Biodiversity",
    # Geography
    "Countries and Regions": "World Geography",
    "Environmental Issues": "Physical Geography",
    "Hydrology": "Rivers & Water Bodies",
    "International Boundaries": "World Geography",
    "Lakes and Deserts": "Physical Geography",
    "Mineral Resources": "Resources & Agriculture",
    "Mountains and Peaks": "Physical Geography",
    "Oceanography": "Physical Geography",
    "Places and Regions": "Indian Geography",
    "Refugee Settlements": "World Geography",
    "Regional Terms": "Indian Geography",
    "River Systems": "Rivers & Water Bodies",
    "River dams": "Rivers & Water Bodies",
    "Rivers and Landforms": "Rivers & Water Bodies",
    "Seasons and Climate": "Climate & Monsoon",
    "Soil Science": "Physical Geography",
    "Tea-producing states": "Indian Geography",
    "Tribes and Languages": "Indian Geography",
    "Wetlands and Lakes": "Rivers & Water Bodies",
    # History
    "Cultural History": "Indian Art & Culture",
    "Cultural Heritage": "Indian Art & Culture",
    "Freedom Fighters": "Modern India",
    "Indian history": "Modern India",
    "Indian scholars": "Indian Art & Culture",
    "Kautilya's Arthashastra": "Ancient India",
    "Land Reforms": "Post-Independence India",
    "Mongol invasion": "Medieval India",
    "Philosophers and Saints": "Indian Art & Culture",
    "Temple History": "Ancient India",
    "Dutch settlements": "Modern India",
    "Cripps Mission": "Modern India",
    # International Relations
    "G20 and Global Governance": "International Organisations",
    "Human Rights": "Global Issues",
    "International organizations": "International Organisations",
    "Maritime Law": "Treaties & Agreements",
    "Military Technology": "Global Issues",
    "United Nations": "International Organisations",
    "Vietnam's economy": "Global Issues",
    # Polity
    "Administration": "Governance & Policy",
    "Anti-Defection Law": "Parliament & Legislature",
    "Awards and Honors": "Governance & Policy",
    "Bank Board Bureau": "Governance & Policy",
    "Citizenship": "Rights & Duties",
    "Constitutional Amendments": "Constitution",
    "Constitutional Government": "Constitution",
    "Constitutional History": "Constitution",
    "Constitutional Provisions": "Constitution",
    "Constitutional Reforms": "Constitution",
    "Deputy Speaker of Lok Sabha": "Parliament & Legislature",
    "Election & Political Parties": "Parliament & Legislature",
    "Elections": "Parliament & Legislature",
    "Federalism": "Federalism & Local Governance",
    "Fifth Schedule of the Constitution": "Constitution",
    "Fundamental Rights": "Rights & Duties",
    "Government of India Act 1919": "Constitution",
    "Labour Laws": "Rights & Duties",
    "Liberty and Democracy": "Rights & Duties",
    "Lok Sabha Powers": "Parliament & Legislature",
    "Ministers and their Ranks": "Executive",
    "Parliamentary Officers": "Parliament & Legislature",
    "State and Citizenship": "Rights & Duties",
    "Tribal Rights": "Rights & Duties",
    "Writs in India": "Judiciary",
    # Science & Technology
    "Astronomy": "Space & Defence",
    "Biofilms": "Biology & Biotechnology",
    "Biological Control": "Biology & Biotechnology",
    "Biology": "Biology & Biotechnology",
    "Biology & Biotechnology": "Biology & Biotechnology",
    "Chemistry": "Physics & Chemistry",
    "Communication Technologies": "IT & Digital",
    "Ecology": "Biology & Biotechnology",
    "Environmental Science": "Biology & Biotechnology",
    "Genetics and Biotechnology": "Biology & Biotechnology",
    "Marine Biology": "Biology & Biotechnology",
    "Materials Science": "Physics & Chemistry",
    "Non-Fungible Tokens": "IT & Digital",
    "Physics": "Physics & Chemistry",
    "Physics & Chemistry": "Physics & Chemistry",
    "Physics and Chemistry": "Physics & Chemistry",
    "Probiotics": "Health & Disease",
    "Quantum Computing": "IT & Digital",
    "Renewable Energy": "Physics & Chemistry",
    "Software as a Service (SaaS)": "IT & Digital",
    "Space & Defence": "Space & Defence",
    "Space Weather": "Space & Defence",
    "Vaccines": "Health & Disease",
    "Virology": "Health & Disease",
    "Web 3.0": "IT & Digital",
    "Zoology": "Biology & Biotechnology",
    # Current Affairs
    "Ayushman Bharat Digital Mission": "Miscellaneous",
    "General": "Miscellaneous",
    "Government Schemes": "Miscellaneous",
    "Sports": "Miscellaneous",
    "Renewable Energy": "Miscellaneous",
}

# ── Connect ───────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print("="*55)
print("UPSC DB Update")
print("="*55)

# ── Step 1: Normalize subtopics ───────────────────────────────────────────────
print("\n[1] Normalizing subtopics...")
rows = conn.execute("SELECT id, topic, subtopic FROM questions").fetchall()
updated = 0
for row in rows:
    sub = (row["subtopic"] or "").strip()
    topic = (row["topic"] or "").strip()

    # Blank subtopic → pick first canonical for that topic
    if not sub:
        canonical_sub = TOPICS.get(topic, ["Miscellaneous"])[0]
        conn.execute("UPDATE questions SET subtopic=? WHERE id=?", [canonical_sub, row["id"]])
        updated += 1
        continue

    # Normalize via map
    if sub in NORMALIZE_SUB:
        new_sub = NORMALIZE_SUB[sub]
        if new_sub != sub:
            conn.execute("UPDATE questions SET subtopic=? WHERE id=?", [new_sub, row["id"]])
            updated += 1
            continue

    # If subtopic not in canonical list for its topic, map to closest
    valid_subs = TOPICS.get(topic, [])
    if valid_subs and sub not in valid_subs:
        # try to find a close match
        best = valid_subs[0]
        for vs in valid_subs:
            if any(word.lower() in sub.lower() for word in vs.split()):
                best = vs
                break
        conn.execute("UPDATE questions SET subtopic=? WHERE id=?", [best, row["id"]])
        updated += 1

conn.commit()
print(f"   Updated {updated} subtopics")

# ── Step 2: Rebuild topics table ──────────────────────────────────────────────
print("\n[2] Rebuilding topics table...")
conn.execute("DELETE FROM topics")

inserted = 0
for parent, subs in TOPICS.items():
    for sub in subs:
        conn.execute(
            "INSERT OR IGNORE INTO topics (parent_topic, name) VALUES (?, ?)",
            [parent, sub]
        )
        inserted += 1

conn.commit()
print(f"   Inserted {inserted} topic entries")

# ── Step 3: Recompute frequency + is_repeated ─────────────────────────────────
print("\n[3] Recomputing frequency & is_repeated...")
# Group by question text similarity (use q_num + question hash as proxy)
# Simple approach: count year_tags length
rows = conn.execute("SELECT id, year_tags FROM questions").fetchall()
updated = 0
for row in rows:
    yt = row["year_tags"] or "[]"
    try:
        import json
        tags = json.loads(yt) if isinstance(yt, str) else yt
        freq = len(tags) if isinstance(tags, list) else 1
    except Exception:
        freq = 1
    is_rep = 1 if freq > 1 else 0
    conn.execute(
        "UPDATE questions SET frequency=?, is_repeated=? WHERE id=?",
        [freq, is_rep, row["id"]]
    )
    updated += 1

conn.commit()
print(f"   Updated {updated} questions")

# ── Step 4: Summary ───────────────────────────────────────────────────────────
print("\n[4] Final topic distribution:")
for year in [2024, 2025]:
    r = conn.execute(
        f"SELECT topic, COUNT(*) as cnt FROM questions WHERE year_first={year} GROUP BY topic ORDER BY cnt DESC"
    ).fetchall()
    print(f"\n  {year}:")
    for row in r:
        print(f"    {row['topic']}: {row['cnt']}")

# Verify no orphan subtopics
orphans = conn.execute("""
    SELECT COUNT(*) FROM questions q
    LEFT JOIN topics t ON t.name = q.subtopic AND t.parent_topic = q.topic
    WHERE t.id IS NULL AND q.subtopic IS NOT NULL
""").fetchone()[0]
print(f"\n  Orphan subtopics remaining: {orphans}")

conn.close()
print("\nDB update complete.")
