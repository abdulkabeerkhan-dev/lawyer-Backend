import os
import json
import time
from typing import Dict, Any, List, Optional

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs', 'retrieval_traces'))
os.makedirs(LOG_DIR, exist_ok=True)


class RetrievalTraceLogger:
    def __init__(self, job_id: str, raw_query: str):
        self.job_id = job_id or f"trace_{int(time.time() * 1000)}"
        self.raw_query = raw_query
        self.trace = {
            'job_id': self.job_id,
            'timestamp': time.time(),
            'raw_query': raw_query,
            'decomposed_subqueries': [],
            'subquery_retrievals': [],
            'coverage_gaps': [],
            'fallback_events': [],
            'final_precedents': [],
            'negative_disclosures': []
        }

    def log_decomposition(self, subqueries: List[str]):
        self.trace['decomposed_subqueries'] = list(subqueries)

    def log_subquery_results(self, subquery: str, dense_count: int, sparse_count: int, top_hits: List[Dict[str, Any]]):
        self.trace['subquery_retrievals'].append({
            'subquery': subquery,
            'dense_count': dense_count,
            'sparse_count': sparse_count,
            'top_hits': [
                {
                    'id': str(h.get('id', '')),
                    'score': float(h.get('score', 0.0)),
                    'citation': str(h.get('metadata', {}).get('citation', '') or h.get('citation', '')),
                    'court': str(h.get('metadata', {}).get('court', '') or h.get('court', ''))
                }
                for h in (top_hits or [])[:5]
            ]
        })

    def log_coverage_gap(self, sub_issue: str, reason: str):
        self.trace['coverage_gaps'].append({
            'sub_issue': sub_issue,
            'reason': reason
        })

    def log_fallback_event(self, target_query: str, portal_urls: List[str], candidates_found: int):
        self.trace['fallback_events'].append({
            'target_query': target_query,
            'portal_urls': portal_urls,
            'candidates_found': candidates_found
        })

    def log_final_context(self, precedents: List[Dict[str, Any]]):
        self.trace['final_precedents'] = [
            {
                'case_id': p.get('case_id'),
                'citation': p.get('citation'),
                'court': p.get('court') or p.get('court_name'),
                'content_type': p.get('content_type'),
                'outcome': p.get('outcome')
            }
            for p in (precedents or [])
        ]

    def log_negative_disclosure(self, ungrounded_issue: str, verified_rule: str):
        self.trace['negative_disclosures'].append({
            'ungrounded_issue': ungrounded_issue,
            'verified_rule': verified_rule
        })

    def write_trace(self):
        try:
            filepath = os.path.join(LOG_DIR, f"{self.job_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.trace, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

