import os
import sys
from dotenv import load_dotenv

load_dotenv('D:/lawyer-Backend/.env')
sys.path.insert(0, 'D:/lawyer-Backend')

from core.turso_client import execute_turso_pipeline

res = execute_turso_pipeline([{"sql": "SELECT name FROM sqlite_master WHERE type='table'"}])
print("Turso tables:", res)
