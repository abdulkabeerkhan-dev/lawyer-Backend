import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

api_key = os.environ.get("PINECONE_API_KEY")
if not api_key:
    print("Set PINECONE_API_KEY as an environment variable and re-run this script.")
    raise SystemExit(1)

pc = Pinecone(api_key=api_key)

index_name = "legal-kb-pk"
desc = pc.describe_index(index_name)
print("Index description:")
print(desc)

embed_config = getattr(desc, "embed", None)
if embed_config:
    print("\nEmbed config:")
    print(f"  model: {embed_config.get('model') if isinstance(embed_config, dict) else getattr(embed_config, 'model', None)}")
    print(f"  field_map: {embed_config.get('field_map') if isinstance(embed_config, dict) else getattr(embed_config, 'field_map', None)}")
else:
    print("\nNo 'embed' config found on this index — it may not be using integrated embedding.")