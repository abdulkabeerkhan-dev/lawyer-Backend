from core.legal_query_planner import StructuredLegalQueryPlan, create_deterministic_fallback_plan

def test_secondary_domain_normalization():
    # Test that unknown/aliased domains do not raise ValidationError
    plan = StructuredLegalQueryPlan(
        query_text="test query",
        primary_domain="family",
        secondary_domains=["property", "matrimonial", "unknown_xyz"]
    )
    assert plan.primary_domain == "family"
    assert plan.secondary_domains == ["civil"], f"Expected ['civil'], got {plan.secondary_domains}"
    print("✓ Test 1: Domain normalization passed")

def test_gold_dowry_query_classification():
    q = "please give me precedent on divorce law where gold was given in place of dowry but was not registered in the nikkah nama"
    plan = create_deterministic_fallback_plan(q)
    assert plan.primary_domain == "family", f"Expected family, got {plan.primary_domain}"
    assert "Family Court" in plan.competent_forum, f"Expected Family Court, got {plan.competent_forum}"
    assert any("FAMILY_COURTS" in p or "Family Courts" in p for p in plan.statutory_provisions), f"Provisions: {plan.statutory_provisions}"
    lane_names = [l["lane"] if isinstance(l, dict) else l.lane_id for l in plan.search_lanes]
    assert any("dowry" in name for name in lane_names), f"Lanes: {lane_names}"
    print("✓ Test 2: Gold/dowry query accurately classified as family law")

if __name__ == "__main__":
    test_secondary_domain_normalization()
    test_gold_dowry_query_classification()
    print("ALL TESTS PASSED!")
