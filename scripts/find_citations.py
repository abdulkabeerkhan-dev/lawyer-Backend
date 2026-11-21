with open("D:/lawyer-Backend/legal_ai/query_engine/query_processor.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "citations" in l.lower() or "precedent_cards" in l.lower() or "precedents" in l.lower():
        if any(k in l for k in ['"citations"', "'citations'", '"precedent_cards"', "'precedent_cards'", '"precedents"', "'precedents'"]):
            print(f"{i+1}: {l.strip()[:110]}")
