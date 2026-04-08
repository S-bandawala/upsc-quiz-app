"""
Write corrected Set A answers based on visual reading of answer key page 1 images.
These replace the old cache files which had Set D answers (last page overwrote Set A).
"""

import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ── 2015 Set A (100 items, NIL dropped) ──
ans_2015 = {
    1:"c",2:"a",3:"b",4:"a",5:"b",6:"d",7:"c",8:"b",9:"b",10:"a",
    11:"c",12:"b",13:"a",14:"b",15:"a",
    16:"b",17:"b",18:"a",19:"c",20:"d",21:"d",22:"c",23:"c",24:"b",25:"c",
    26:"d",27:"b",28:"a",29:"c",30:"d",
    31:"c",32:"c",33:"b",34:"c",35:"b",36:"d",37:"a",38:"d",39:"d",40:"b",
    41:"b",42:"d",43:"a",44:"d",45:"c",
    46:"b",47:"c",48:"b",49:"a",50:"c",51:"a",52:"d",53:"b",54:"b",55:"b",
    56:"d",57:"b",58:"c",59:"a",60:"c",
    61:"d",62:"b",63:"c",64:"c",65:"b",66:"b",67:"d",68:"a",69:"a",70:"d",
    71:"a",72:"c",73:"d",74:"c",75:"a",
    76:"c",77:"b",78:"a",79:"c",80:"b",81:"b",82:"d",83:"d",84:"c",85:"c",
    86:"c",87:"c",88:"a",89:"b",90:"b",
    91:"d",92:"d",93:"d",94:"c",95:"a",96:"a",97:"b",98:"a",99:"c",100:"c",
}

# ── 2017 Set A (100 items, NIL dropped) ──
ans_2017 = {
    1:"d",2:"c",3:"a",4:"a",5:"a",6:"b",7:"b",8:"c",9:"a",10:"b",
    11:"a",12:"b",13:"c",14:"c",15:"d",
    16:"b",17:"d",18:"c",19:"c",20:"b",21:"c",22:"b",23:"a",24:"b",25:"d",
    26:"d",27:"a",28:"d",29:"c",30:"b",
    31:"c",32:"a",33:"c",34:"c",35:"d",36:"d",37:"b",38:"b",39:"c",40:"a",
    41:"d",42:"a",43:"a",44:"a",45:"d",
    46:"c",47:"a",48:"a",49:"b",50:"d",51:"b",52:"a",53:"b",54:"c",55:"d",
    56:"b",57:"c",58:"b",59:"c",60:"b",
    61:"b",62:"d",63:"d",64:"b",65:"b",66:"b",67:"b",68:"b",69:"a",70:"a",
    71:"c",72:"b",73:"d",74:"c",75:"a",
    76:"d",77:"b",78:"c",79:"c",80:"b",81:"a",82:"a",83:"a",84:"c",85:"d",
    86:"c",87:"b",88:"a",89:"b",90:"d",
    91:"a",92:"a",93:"c",94:"d",95:"b",96:"b",97:"c",98:"c",99:"c",100:"d",
}

# ── 2018 Set A (100 items, 00 dropped) ──
ans_2018 = {
    1:"b",2:"c",3:"c",4:"b",5:"a",6:"c",7:"a",8:"d",9:"c",10:"a",
    11:"c",12:"d",13:"a",14:"d",15:"c",
    16:"a",17:"c",18:"d",19:"a",20:"b",21:"b",22:"b",23:"a",24:"b",25:"b",
    26:"d",27:"d",28:"a",29:"a",30:"a",
    31:"c",32:"a",33:"a",34:"c",35:"b",36:"b",37:"b",38:"b",39:"a",40:"b",
    41:"c",42:"d",43:"c",44:"b",45:"c",
    46:"b",47:"c",48:"c",49:"c",50:"d",51:"c",52:"c",53:"b",54:"a",55:"d",
    56:"c",57:"c",58:"c",59:"c",60:"d",
    61:"a",62:"d",63:"b",64:"b",65:"a",66:"b",67:"d",68:"d",69:"c",70:"d",
    71:"b",72:"d",73:"b",74:"c",75:"c",
    76:"d",77:"a",78:"c",79:"a",80:"b",81:"b",82:"b",83:"b",84:"c",85:"a",
    86:"b",87:"d",88:"c",89:"b",90:"b",
    91:"b",92:"c",93:"b",94:"a",95:"a",96:"b",97:"c",98:"a",99:"d",100:"b",
}

# ── 2019 Set A (100 items, NIL dropped) ──
ans_2019 = {
    1:"d",2:"b",3:"c",4:"a",5:"c",6:"d",7:"c",8:"a",9:"d",10:"a",
    11:"d",12:"a",13:"d",14:"b",15:"d",
    16:"a",17:"c",18:"d",19:"c",20:"a",21:"a",22:"a",23:"a",24:"b",25:"d",
    26:"d",27:"a",28:"d",29:"c",30:"a",
    31:"d",32:"d",33:"c",34:"d",35:"d",36:"b",37:"b",38:"a",39:"a",40:"c",
    41:"d",42:"d",43:"b",44:"b",45:"b",
    46:"c",47:"a",48:"a",49:"a",50:"b",51:"c",52:"b",53:"c",54:"c",55:"b",
    56:"b",57:"c",58:"b",59:"c",60:"c",
    61:"b",62:"a",63:"d",64:"b",65:"b",66:"c",67:"d",68:"a",69:"a",70:"a",
    71:"a",72:"d",73:"a",74:"b",75:"d",
    76:"c",77:"a",78:"c",79:"c",80:"d",81:"d",82:"a",83:"a",84:"d",85:"d",
    86:"d",87:"a",88:"c",89:"d",90:"b",
    91:"b",92:"b",93:"a",94:"c",95:"d",96:"a",97:"b",98:"a",99:"a",100:"b",
}

# ── 2020 Set A (100 items, 02 dropped: Q27, Q52) ──
ans_2020 = {
    1:"b",2:"b",3:"d",4:"d",5:"b",6:"d",7:"d",8:"d",9:"a",10:"c",
    11:"b",12:"a",13:"d",14:"a",15:"d",16:"d",17:"d",18:"d",19:"d",20:"c",
    21:"b",22:"b",23:"a",24:"c",25:"c",26:"a",28:"a",29:"a",30:"a",
    # Q27 dropped (X), Q52 dropped (X)
    31:"c",32:"b",33:"b",34:"d",35:"d",36:"c",37:"d",38:"b",39:"c",40:"d",
    41:"c",42:"d",43:"d",44:"d",45:"b",46:"a",47:"c",48:"a",49:"d",50:"d",
    51:"b",53:"a",54:"d",55:"b",56:"c",57:"b",58:"b",59:"b",60:"b",
    61:"c",62:"a",63:"d",64:"b",65:"a",66:"b",67:"a",68:"c",69:"d",70:"c",
    71:"b",72:"a",73:"c",74:"a",75:"a",76:"d",77:"a",78:"a",79:"d",80:"d",
    81:"a",82:"a",83:"d",84:"a",85:"a",86:"a",87:"a",88:"d",89:"c",90:"a",
    91:"c",92:"d",93:"b",94:"b",95:"c",96:"d",97:"a",98:"b",99:"c",100:"c",
}

# ── 2021 Set A (100 items, 01 dropped: Q80) ──
ans_2021 = {
    1:"c",2:"b",3:"b",4:"a",5:"b",6:"d",7:"a",8:"a",9:"d",10:"d",
    11:"c",12:"a",13:"b",14:"c",15:"b",16:"a",17:"b",18:"d",19:"a",20:"c",
    21:"c",22:"b",23:"d",24:"a",25:"b",26:"c",27:"c",28:"c",29:"a",30:"d",
    31:"c",32:"a",33:"a",34:"b",35:"d",36:"c",37:"d",38:"a",39:"c",40:"b",
    41:"b",42:"b",43:"a",44:"c",45:"a",46:"c",47:"d",48:"b",49:"a",50:"b",
    51:"b",52:"b",53:"d",54:"d",55:"b",56:"b",57:"a",58:"c",59:"d",60:"b",
    61:"c",62:"b",63:"b",64:"b",65:"c",66:"c",67:"b",68:"c",69:"a",70:"b",
    71:"a",72:"c",73:"d",74:"b",75:"d",76:"d",77:"c",78:"b",79:"c",
    # Q80 dropped
    81:"d",82:"b",83:"b",84:"d",85:"a",86:"a",87:"a",88:"a",89:"a",90:"d",
    91:"b",92:"b",93:"b",94:"d",95:"d",96:"d",97:"c",98:"c",99:"b",100:"d",
}

# ── 2023 Set A (100 items, 01 dropped) ──
# Reading from the clear Set A image (page 1)
ans_2023 = {
    1:"b",2:"b",3:"b",4:"a",5:"d",6:"d",7:"c",8:"a",9:"d",10:"d",
    11:"c",12:"c",13:"a",14:"a",15:"a",
    16:"b",17:"b",18:"c",19:"b",20:"b",
    21:"a",22:"a",23:"b",24:"a",25:"b",26:"b",27:"c",28:"c",29:"b",30:"b",
    31:"c",32:"a",33:"c",34:"a",35:"b",36:"d",37:"a",38:"b",39:"b",40:"c",
    41:"a",42:"b",43:"b",44:"d",45:"b",46:"b",47:"b",48:"a",49:"c",50:"d",
    51:"a",52:"d",53:"a",54:"c",55:"b",56:"d",57:"c",58:"a",59:"d",60:"c",
    61:"a",62:"c",63:"d",64:"d",65:"c",66:"d",67:"a",68:"b",69:"b",70:"a",
    71:"b",72:"c",73:"d",74:"a",75:"b",76:"c",77:"b",78:"a",79:"b",80:"a",
    81:"a",82:"b",83:"a",84:"d",85:"c",86:"c",87:"c",88:"d",89:"a",90:"d",
    91:"b",92:"a",93:"b",94:"c",95:"d",96:"a",97:"c",98:"b",99:"c",100:"c",
}

# We'll write these to cache and handle 2022 and 2024 separately (need better image)

ALL_ANSWERS = {
    2015: ans_2015,
    2017: ans_2017,
    2018: ans_2018,
    2019: ans_2019,
    2020: ans_2020,
    2021: ans_2021,
    2023: ans_2023,
}

def main():
    print("Writing corrected Set A answer caches...")

    for year, answers in ALL_ANSWERS.items():
        cache_file = CACHE_DIR / f"{year}_answers.json"

        # Load old answers for comparison
        old = {}
        if cache_file.exists():
            old = json.loads(cache_file.read_text(encoding="utf-8"))

        # Convert to string keys for JSON
        str_answers = {str(k): v for k, v in answers.items()}

        # Count changes
        changed = 0
        for k, v in str_answers.items():
            if old.get(k) != v:
                changed += 1

        cache_file.write_text(json.dumps(str_answers, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{year}] {len(answers)} answers written, {changed} changed from old cache")

    # Now re-merge all answers into raw_questions.json
    print("\nRe-merging corrected answers into raw_questions.json...")

    raw_path = DATA_DIR / "raw_questions.json"
    if not raw_path.exists():
        print("raw_questions.json not found!")
        return

    with open(raw_path, encoding="utf-8") as f:
        questions = json.load(f)

    # Load all answer caches
    all_answers = {}
    for year_file in CACHE_DIR.glob("*_answers.json"):
        year = int(year_file.stem.split("_")[0])
        year_ans = json.loads(year_file.read_text(encoding="utf-8"))
        all_answers[year] = {int(k): v for k, v in year_ans.items()}

    # Apply answers
    updated = 0
    with_answer = 0
    for q in questions:
        year_ans = all_answers.get(q["year"], {})
        old_ans = q.get("correct_option")
        new_ans = year_ans.get(q.get("q_num"))
        q["correct_option"] = new_ans
        if new_ans:
            with_answer += 1
        if old_ans != new_ans:
            updated += 1

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    print(f"Answers changed: {updated}")
    print(f"Total with answers: {with_answer} / {len(questions)}")

    # Also update beta_questions.json if it exists
    beta_path = DATA_DIR / "beta_questions.json"
    if beta_path.exists():
        with open(beta_path, encoding="utf-8") as f:
            beta_qs = json.load(f)

        beta_updated = 0
        for q in beta_qs:
            year_ans = all_answers.get(q.get("year_first", q.get("year")), {})
            old_ans = q.get("correct_option")
            new_ans = year_ans.get(q.get("q_num"))
            q["correct_option"] = new_ans
            if old_ans != new_ans:
                beta_updated += 1

        with open(beta_path, "w", encoding="utf-8") as f:
            json.dump(beta_qs, f, ensure_ascii=False, indent=2)
        print(f"Beta questions updated: {beta_updated}")

    print("\nNext: run classify_and_build_db.py to rebuild the database")


if __name__ == "__main__":
    main()
