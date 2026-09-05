import os
import sys

print("Initializing application environment...")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Uvicorn server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port)
