import os
import json
from dotenv import load_dotenv
from pinecone import Pinecone
import voyageai

load_dotenv()

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "judgments")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")

def main():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)
    voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    
    # Generate a generic vector for sampling
    print("Generating generic embedding for sampling...")
    res = voyage_client.embed(["Pakistan law supreme court cases"], model="voyage-law-2", input_type="document")
    generic_vector = res.embeddings[0]

    # Task 1: Audit corpus depth (Counts per High Court & Year Range)
    courts = [
        "Supreme Court of Pakistan", 
        "Lahore High Court", 
        "Sindh High Court", 
        "Peshawar High Court", 
        "Islamabad High Court", 
        "Balochistan High Court",
        "Federal Shariat Court"
    ]
    decades = [
        (1950, 1960), (1960, 1970), (1970, 1980), (1980, 1990),
        (1990, 2000), (2000, 2010), (2010, 2020), (2020, 2030)
    ]

    print("\n--- CORPUS DEPTH AUDIT ---")
    audit_results = {}
    for court in courts:
        audit_results[court] = {}
        total_for_court = 0
        for start, end in decades:
            filter_dict = {
                "court": {"$eq": court},
                "year": {"$gte": start, "$lt": end}
            }
            try:
                # Query with a dummy vector and top_k 10000 to count items.
                matches = index.query(
                    vector=generic_vector,
                    filter=filter_dict,
                    top_k=10000,
                    namespace=NAMESPACE,
                    include_metadata=False
                )
                count = len(matches.get("matches", []))
                audit_results[court][f"{start}s"] = count
                total_for_court += count
            except Exception as e:
                print(f"Error querying {court} {start}s: {e}")
                audit_results[court][f"{start}s"] = "Error"
        audit_results[court]["Total (up to 10k/decade)"] = total_for_court
        print(f"{court}: {total_for_court} total sampled chunks")
        for k, v in audit_results[court].items():
            if k != "Total (up to 10k/decade)" and v > 0:
                print(f"  {k}: {v} chunks")

    # Task 2: Check Statute and Constitution Coverage
    print("\n--- STATUTE & CONSTITUTION COVERAGE ---")
    targets = [
        "Article 175",
        "Article 199",
        "Legal Practitioners Act",
        "CrPC",
        "CPC"
    ]
    
    for target in targets:
        print(f"\nSearching for target: {target}")
        res = voyage_client.embed([target], model="voyage-law-2", input_type="query")
        target_vector = res.embeddings[0]
        
        matches = index.query(
            vector=target_vector,
            top_k=5,
            namespace=NAMESPACE,
            include_metadata=True
        )
        
        chunks = matches.get("matches", [])
        if not chunks:
            print(f"[FAIL] '{target}' - ZERO chunks retrieved. GAP CONFIRMED.")
        else:
            found_in_text = 0
            for c in chunks:
                text = c.get("metadata", {}).get("text", "")
                if target.lower() in text.lower():
                    found_in_text += 1
            print(f"[PASS] '{target}' - Found {len(chunks)} chunks in top 5.")
            print(f"   {found_in_text}/5 chunks explicitly contain the string '{target}'.")
            if found_in_text == 0:
                print("   [WARNING] The chunks retrieved don't explicitly mention the target string. Could be semantic, or could be hallucinated retrieval.")
                print(f"   Top chunk preview: {chunks[0].get('metadata', {}).get('text', '')[:200]}...")

if __name__ == "__main__":
    main()
