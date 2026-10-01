"""
Hermetic Mock Supabase Client for Offline Unit Testing.
Provides in-memory mock responses for full_judgments and precedent_status tables
so that unit tests do not require network access, active API keys, or live databases.
"""

from typing import Dict, Any, List, Optional


class MockSupabaseResult:
    def __init__(self, data: List[Dict[str, Any]]):
        self.data = data


class MockQueryBuilder:
    def __init__(self, table_name: str, db_data: Dict[str, List[Dict[str, Any]]]):
        self.table_name = table_name
        self.db_data = db_data
        self._filters: List[tuple] = []
        self._limit: Optional[int] = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, column: str, value: Any):
        self._filters.append((column, value, "eq"))
        return self

    def ilike(self, column: str, pattern: str):
        self._filters.append((column, pattern, "ilike"))
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def execute(self):
        rows = self.db_data.get(self.table_name, [])
        filtered = []
        for r in rows:
            match = True
            for col, val, op in self._filters:
                r_val = r.get(col, "")
                if op == "eq":
                    if str(r_val).strip().upper() != str(val).strip().upper():
                        match = False
                        break
                elif op == "ilike":
                    pat = str(val).replace("%", "").strip().lower()
                    if pat not in str(r_val).lower():
                        match = False
                        break
            if match:
                filtered.append(dict(r))
        if self._limit is not None:
            filtered = filtered[:self._limit]
        return MockSupabaseResult(filtered)


def get_default_mock_db() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "full_judgments": [
            {
                "id": "1958_PLD_SC_138",
                "case_id": "1958_PLD_SC_138",
                "neutral_citation": "PLD 1958 SC 138",
                "case_title": "Havover Fire Insurance Company v. Muralidhar Banechnd",
                "court_name": "Supreme Court of Pakistan",
                "decision_date": "1958-01-01",
                "full_text": "Havover Fire Insurance Company v. Muralidhar Banechnd. " + ("Judgment text of Supreme Court in insurance appeal. " * 30)
            },
            {
                "id": "2006_YLR_1206",
                "case_id": "2006_YLR_1206",
                "neutral_citation": "2006 YLR 1206",
                "case_title": "FAIZ ULLAH VS GHULAM RASUL",
                "court_name": "Lahore High Court",
                "decision_date": "2006-01-01",
                "full_text": "FAIZ ULLAH VS GHULAM RASUL. Detailed judgment text of Lahore High Court exceeding one thousand characters. " + ("High Court judgment content and legal analysis on merits. " * 25)
            },
            {
                "id": "1958_PLD_SC_533",
                "case_id": "1958_PLD_SC_533",
                "neutral_citation": "PLD 1958 SC 533",
                "case_title": "State v. Dosso",
                "court_name": "Supreme Court of Pakistan",
                "decision_date": "1958-01-01",
                "full_text": "State v. Dosso. Supreme Court judgment on doctrine of revolutionary legality. " + ("Detailed text. " * 20)
            },
            {
                "id": "1972_PLD_SC_139",
                "case_id": "1972_PLD_SC_139",
                "neutral_citation": "PLD 1972 SC 139",
                "case_title": "Miss Asma Jilani v. Government Of The Punjab",
                "court_name": "Supreme Court of Pakistan",
                "decision_date": "1972-01-01",
                "full_text": "Miss Asma Jilani v. Government Of The Punjab. Supreme Court judgment overruling Dosso. " + ("Detailed text. " * 20)
            },
            {
                "id": "2013_SCMR_51",
                "case_id": "2013_SCMR_51",
                "neutral_citation": "2013 SCMR 51",
                "case_title": "Mian Allah Ditta v. The State",
                "court_name": "Supreme Court of Pakistan",
                "decision_date": "2013-01-01",
                "full_text": "Mian Allah Ditta v. The State. Supreme Court judgment on Section 489-F PPC. " + ("Detailed text. " * 20)
            },
            {
                "id": "2021_SCMR_2092",
                "case_id": "2021_SCMR_2092",
                "neutral_citation": "2021 SCMR 2092",
                "case_title": "Muhammad Nasir Shafique v. The State",
                "court_name": "Supreme Court of Pakistan",
                "decision_date": "2021-01-01",
                "full_text": "Muhammad Nasir Shafique v. The State. Supreme Court judgment. " + ("Detailed text. " * 20)
            }
        ],
        "precedent_status": []
    }


class MockSupabaseClient:
    def __init__(self, db_data: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self.db_data = db_data if db_data is not None else get_default_mock_db()

    def table(self, table_name: str):
        return MockQueryBuilder(table_name, self.db_data)
