import unittest
import json
from legal_ai.analytics.pipeline_tracer import PipelineTracer

class TestPipelineTracer(unittest.TestCase):
    def test_pipeline_tracer_records_stages_and_fallbacks(self):
        tracer = PipelineTracer(job_id="test-job-001", query_text="489-F cheque bail")
        
        # Record stage 1: query_planning
        tracer.record_stage(
            stage="query_planning",
            fallbacks={"planner_fallback": False},
            extra={"provisions": ["Section 489-F PPC"]}
        )
        
        # Record stage 2: retrieval_merged
        candidates = [
            {"case_id": f"case_{i}", "title": f"Title {i}", "court": "Supreme Court of Pakistan", "score": 1.0 - i*0.05}
            for i in range(15)
        ]
        tracer.record_stage(
            stage="retrieval_merged",
            candidates=candidates,
            fallbacks={"supabase_breaker": True}
        )
        
        # Record stage 3: rerank
        tracer.record_stage(
            stage="rerank",
            candidates=candidates[:8],
            fallbacks={"rerank_fallback": False}
        )
        
        # Record stage 4: domain_gate
        tracer.record_stage(
            stage="domain_gate",
            candidates=candidates[:6],
            fallbacks={"gate_bypass": False}
        )

        # Record stage 5: verification
        tracer.record_stage(
            stage="verification",
            fallbacks={"verification_block": True, "canned_fallback": False},
            extra={"violations_count": 3}
        )
        
        data = tracer.to_dict()
        self.assertEqual(data["job_id"], "test-job-001")
        self.assertEqual(data["query_text"], "489-F cheque bail")
        self.assertEqual(len(data["stages"]), 5)
        
        # Verify top_10 cap in retrieval_merged stage
        stage_merged = next(s for s in data["stages"] if s["stage"] == "retrieval_merged")
        self.assertEqual(len(stage_merged["top_10"]), 10)
        self.assertEqual(stage_merged["top_10"][0]["case_id"], "case_0")
        self.assertTrue(stage_merged["fallbacks_fired"]["supabase_breaker"])
        
        # Verify JSON serializability
        json_str = tracer.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["job_id"], "test-job-001")

if __name__ == "__main__":
    unittest.main()
