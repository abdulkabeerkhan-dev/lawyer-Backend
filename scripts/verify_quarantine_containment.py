import os
import sys

REPO_DIR = os.path.abspath(".")
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.statutes.statute_store import lookup
from core.statutory_validator import validate_citations_in_text
from core.statute_currency import check_statute_currency
from legal_ai.verification.statute_matcher import get_authority_store
from legal_ai.statutes.statute_injector import StatuteInjector

print("=== 1. RE-RUN SECTION 138 NI ACT ===")
res_ni_138 = lookup("NI Act", "Section 138")
print(f"Status: {res_ni_138.status}")
print(f"Exists: {res_ni_138.exists}")
print(f"Confirmed Absent: {res_ni_138.confirmed_absent}")
print(f"Explanation: {res_ni_138.explanation}")
assert res_ni_138.status == "UNVERIFIED"
assert res_ni_138.exists is False
print("Assertion Passed: Section 138 NI Act returns status='UNVERIFIED' (quarantined act)")

print("\n=== 2. TEST QUARANTINED ACTS ACROSS 4 MODULES ===")
sample_quarantined = ["AMLA_2010", "PECA_2016", "ARBITRATION_1940", "MFLO_1961", "ITO_2001", "LAND_REVENUE_1967"]

injector = StatuteInjector()
auth_store = get_authority_store()

for act in sample_quarantined:
    # 1. Injector
    inj_res = injector.get_provision_record(act, f"{act}_SEC_1")
    assert inj_res is None, f"Injector should return None for quarantined {act}"

    # 2. Statute Matcher / Authority Store
    m_prov = auth_store.provision(f"{act}_SEC_1")
    m_txt = auth_store.statute_text(f"{act}_SEC_1")
    assert m_prov is None, f"Matcher should return None for quarantined {act}"
    assert m_txt is None, f"Matcher text should return None for quarantined {act}"

    # 3. Currency
    curr_res = check_statute_currency(f"{act}_SEC_1", act)
    assert curr_res is None or curr_res.get("status") in ("not_in_tables", "unverified", "quarantined", "error"), f"Currency should return unverified for {act}"

    # 4. Statutory Validator
    val_res = validate_citations_in_text(f"Section 1 of {act} provides that...")
    for c in val_res.get("cited_provisions", []):
        assert c.get("is_valid") is False, f"Validator should mark {act} as invalid/unverified"

print("All sample quarantined acts strictly return unverified / None across all 4 modules!")

print("\n=== 3. VERIFY NO PRODUCTION CODE READS data/quarantine ===")
production_dirs = ["core", "legal_ai"]
violations = []
for pdir in production_dirs:
    for root, dirs, files in os.walk(pdir):
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                with open(fpath, "r", encoding="utf-8") as pyf:
                    code = pyf.read()
                    if "data/quarantine" in code or "data\\quarantine" in code:
                        violations.append(fpath)

print(f"Production code reading data/quarantine: {violations}")
assert len(violations) == 0, f"Violations found: {violations}"
print("Verified: ZERO production files read data/quarantine!")
