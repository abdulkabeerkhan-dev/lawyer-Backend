import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(".env")

from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

for model_id in ["claude-haiku-4-5-20251001", "claude-3-5-sonnet-20241022"]:
    try:
        resp = client.messages.create(
            model=model_id,
            max_tokens=20,
            messages=[{"role": "user", "content": "Respond with 'OK' and the model name."}]
        )
        print(f"Model {model_id}: SUCCESS -> {resp.content[0].text.strip()}")
    except Exception as e:
        print(f"Model {model_id}: FAILED -> {e}")
