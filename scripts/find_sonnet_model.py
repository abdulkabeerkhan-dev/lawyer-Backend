import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(".env")
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

for m in ["claude-3-5-sonnet-latest", "claude-3-5-sonnet-20240620", "claude-3-7-sonnet-20250219", "claude-3-sonnet-20240229"]:
    try:
        resp = client.messages.create(
            model=m,
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}]
        )
        print(f"{m}: SUCCESS")
    except Exception as e:
        print(f"{m}: {e}")
