with open("legal_ai/synthesis/memorandum_generator.py", "rb") as f:
    content = f.read().decode("utf-8")

old_str = "1. Zero Disclaimer Pollution: Purges prototype disclaimers, currency warning tags,"
new_str = "1. Clean Opinion Synthesis: Generates structured legal opinions"

if old_str in content:
    content = content.replace(old_str, new_str)
    with open("legal_ai/synthesis/memorandum_generator.py", "wb") as f:
        f.write(content.encode("utf-8"))
    print("Successfully replaced in memorandum_generator.py")
else:
    print("old_str not found in memorandum_generator.py")
