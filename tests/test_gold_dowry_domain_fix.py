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

def test_all_domain_fallback_classifications():
    # 1. Taxation
    tax_q = "show cause notice issued by FBR under section 122 of income tax ordinance for unexplained income"
    tax_plan = create_deterministic_fallback_plan(tax_q)
    assert tax_plan.primary_domain == "taxation", f"Expected taxation, got {tax_plan.primary_domain}"
    assert "Inland Revenue" in tax_plan.competent_forum

    # 2. Labour
    labour_q = "workman terminated without inquiry unfair labour practice petition before NIRC"
    labour_plan = create_deterministic_fallback_plan(labour_q)
    assert labour_plan.primary_domain == "labour", f"Expected labour, got {labour_plan.primary_domain}"
    assert "NIRC" in labour_plan.competent_forum or "Labour Court" in labour_plan.competent_forum

    # 3. Environmental
    env_q = "factory discharging toxic chemical effluent without EIA under PEPA 1997"
    env_plan = create_deterministic_fallback_plan(env_q)
    assert env_plan.primary_domain == "environmental", f"Expected environmental, got {env_plan.primary_domain}"
    assert "Environmental Protection Tribunal" in env_plan.competent_forum

    # 4. Family / Dowry / Bridal Gifts
    fam_q = "suit for recovery of jahez and bridal gifts not entered in nikahnama"
    fam_plan = create_deterministic_fallback_plan(fam_q)
    assert fam_plan.primary_domain == "family", f"Expected family, got {fam_plan.primary_domain}"

    # 5. Cybercrime
    cyber_q = "blackmail and online harassment on social media complaint under PECA 2016"
    cyber_plan = create_deterministic_fallback_plan(cyber_q)
    assert cyber_plan.primary_domain == "cybercrime", f"Expected cybercrime, got {cyber_plan.primary_domain}"

    # 6. Intellectual Property
    ip_q = "suit for infringement of registered trademark and passing off"
    ip_plan = create_deterministic_fallback_plan(ip_q)
    assert ip_plan.primary_domain == "intellectual_property", f"Expected intellectual_property, got {ip_plan.primary_domain}"

    print("✓ Test 3: All domains correctly classified")

if __name__ == "__main__":
    test_secondary_domain_normalization()
    test_gold_dowry_query_classification()
    test_all_domain_fallback_classifications()
    print("ALL TESTS PASSED!")
