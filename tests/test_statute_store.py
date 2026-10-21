"""
tests/test_statute_store.py

Unit tests for Section-Addressable Statute Store & Schedule II Lookup.
"""

import pytest
from legal_ai.statutes.statute_store import get_statute_store, lookup


def test_ni_act_138_confirmed_absent():
    res = lookup("NI Act", "Section 138")
    assert res.status == "CONFIRMED_ABSENT"
    assert res.exists is False
    assert res.confirmed_absent is True
    assert "Section 489-F PPC" in (res.pakistani_equivalent or "")
    assert "Negotiable Instruments Act" in (res.explanation or "")


def test_ni_act_118_exists():
    res = lookup("NI Act", "Section 118")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.confirmed_absent is False
    assert "Presumptions" in (res.title or "")


def test_indian_penal_code_foreign_absent():
    res = lookup("Indian Penal Code", "Section 420")
    assert res.status == "CONFIRMED_ABSENT"
    assert res.exists is False
    assert res.confirmed_absent is True
    assert res.is_foreign_statute is True
    assert "Pakistan Penal Code" in (res.pakistani_equivalent or "")
    # CrPC Schedule II for s.420 should be attached
    assert res.schedule_ii is not None
    assert res.schedule_ii["cognizable"] is True
    assert res.schedule_ii["bailable"] is False
    assert res.schedule_ii["max_imprisonment_years"] == 7


def test_cpc_order_xxxix_rule_2a_absent_and_rule_2_3_exists():
    res = lookup("CPC", "Order XXXIX Rule 2A")
    assert res.status == "CONFIRMED_ABSENT"
    assert res.exists is False
    assert res.confirmed_absent is True
    assert "Order XXXIX Rule 2(3) CPC" in res.pakistani_equivalent

    # And Rule 2(3) exists with authentic Pakistan Code text
    res_2_3 = lookup("CPC", "Order XXXIX Rule 2(3)")
    assert res_2_3.status == "EXISTS"
    assert res_2_3.exists is True
    assert res_2_3.text is not None
    assert "disobedience" in res_2_3.text.lower()
    assert "civil prison" in res_2_3.text.lower()
    assert "six months" in res_2_3.text.lower()


def test_ppc_section_489f_schedule_ii():
    res = lookup("PPC", "Section 489-F")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.text is not None
    assert "dishonestly issues a cheque" in res.text.lower()
    assert res.schedule_ii is not None
    assert res.schedule_ii["cognizable"] is True
    assert res.schedule_ii["bailable"] is False
    assert res.schedule_ii["bailable_status"] == "Non-bailable"
    assert res.schedule_ii["max_imprisonment_years"] == 3


def test_ppc_section_420_schedule_ii():
    res = lookup("PPC", "Section 420")
    assert res.status == "EXISTS"
    assert res.exists is True
    assert res.text is not None
    assert "cheats" in res.text.lower()
    assert res.schedule_ii is not None
    assert res.schedule_ii["cognizable"] is True
    assert res.schedule_ii["bailable"] is False
    assert "non-bailable" in res.schedule_ii["bailable_status"].lower() or "not bailable" in res.schedule_ii["bailable_status"].lower()




def test_unverified_provision():
    res = lookup("NonExistentAct123", "Section 999")
    assert res.status == "UNVERIFIED"
    assert res.exists is False
    assert res.confirmed_absent is False
    assert "Could not verify" in (res.explanation or "")


def test_extract_provisions_from_query():
    store = get_statute_store()
    
    q1 = "What is the punishment under Section 138 of the Negotiable Instruments Act in Pakistan?"
    extracted1 = store.extract_provisions_from_query(q1)
    assert len(extracted1) == 1
    assert "Negotiable Instruments Act" in extracted1[0][0]
    assert "138" in extracted1[0][1]

    q2 = "Punishment under Section 420 of the Indian Penal Code in Pakistan?"
    extracted2 = store.extract_provisions_from_query(q2)
    assert len(extracted2) == 1
    assert "Indian Penal Code" in extracted2[0][0]
    assert "420" in extracted2[0][1]

    q3 = "Injunction under Order XXXIX Rule 2A CPC for breach of a stay order?"
    extracted3 = store.extract_provisions_from_query(q3)
    assert len(extracted3) == 1
    assert "CPC" in extracted3[0][0]
    assert "2A" in extracted3[0][1]

    q4 = "Can a security cheque attract 489-F?"
    extracted4 = store.extract_provisions_from_query(q4)
    assert len(extracted4) == 1
    assert "PPC" in extracted4[0][0]
    assert "489-F" in extracted4[0][1]
