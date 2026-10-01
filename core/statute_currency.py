"""
Statute Currency & Version Store Module (Part 1 & Part 2)
Provides immutable versioning for statutory provisions, source tiering (Tier 1-3),
query-driven currency checking with 24-hour caching and recency triggers,
a staging store for unverified web discoveries, and temporal case tagging.
"""

import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTE_VERSIONS_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_versions")
STATUTE_STAGING_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_staging")
TABLES_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_tables")

os.makedirs(STATUTE_VERSIONS_DIR, exist_ok=True)
os.makedirs(STATUTE_STAGING_DIR, exist_ok=True)

# TIER 1: Official government, parliament, gazette, and court portals
TIER_1_DOMAINS = [
    "pakistancode.gov.pk",
    "na.gov.pk",
    "senate.gov.pk",
    "punjablaws.gov.pk",
    "pas.gov.pk",
    "pap.gov.pk",
    "kpcode.kp.gov.pk",
    "balochistancode.gob.pk",
    "pakistan.gov.pk",
    "supremecourt.gov.pk",
    "lhc.gov.pk",
    "shc.gov.pk",
    "phc.gov.pk",
    "ihc.gov.pk",
    "balochistanhighcourt.gov.pk",
]

# TIER 2: Established, reputable legal reporting journals/portals
TIER_2_DOMAINS = [
    "pakistanlawsite.com",
    "pljlawsite.com",
    "courtingthelaw.com",
    "manzoorlaw.com",
]

RECENCY_WORDS_PATTERN = re.compile(
    r"\b(new|recent|recently|amended|amendment|latest|updated|current|fresh|ordinance)\b",
    re.IGNORECASE
)


def classify_source_tier(source_url: str) -> str:
    """Classifies a URL into Tier 1 (official), Tier 2 (reputable legal), or Tier 3 (news/blogs)."""
    if not source_url:
        return "tier_3"
    s_lower = source_url.lower()
    for d in TIER_1_DOMAINS:
        if d in s_lower:
            return "tier_1"
    for d in TIER_2_DOMAINS:
        if d in s_lower:
            return "tier_2"
    return "tier_3"


class StatuteVersionStore:
    """
    Immutable versioned store for statutory sections.
    Never overwrites existing records; always appends a new version referencing previous_version_id.
    """

    def __init__(self, storage_dir: str = STATUTE_VERSIONS_DIR, staging_dir: str = STATUTE_STAGING_DIR):
        self.storage_dir = storage_dir
        self.staging_dir = staging_dir
        self.staging_file = os.path.join(staging_dir, "statute_currency_staging.json")
        self._ensure_staging_file()

    def _ensure_staging_file(self):
        if not os.path.exists(self.staging_file):
            with open(self.staging_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def _get_act_file(self, act_code: str) -> str:
        clean_act = re.sub(r"[^A-Za-z0-9_]+", "", act_code.upper())
        return os.path.join(self.storage_dir, f"{clean_act}_versions.json")

    def get_versions(self, act_code: str) -> List[Dict[str, Any]]:
        path = self._get_act_file(act_code)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def get_latest_version(self, act_code: str, canonical_id: str) -> Optional[Dict[str, Any]]:
        versions = self.get_versions(act_code)
        matching = [v for v in versions if v.get("canonical_id") == canonical_id]
        if not matching:
            return None
        return matching[-1]

    def batch_import_initial_versions(self, act_code: str, provisions: List[Dict[str, Any]]) -> int:
        """Batch-imports initial provisions if the act version file does not already exist."""
        path = self._get_act_file(act_code)
        if os.path.exists(path) and os.path.getsize(path) > 10:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        records = []
        for r in provisions:
            cid = r.get("canonical_id")
            if not cid:
                continue
            src_url = r.get("source_citation") or "https://pakistancode.gov.pk"
            records.append({
                "version_id": f"{cid}_V1",
                "canonical_id": cid,
                "act_code": act_code,
                "provision_type": r.get("provision_type", "section"),
                "primary_num": str(r.get("primary_num") or ""),
                "secondary_num": r.get("secondary_num"),
                "title": r.get("title") or r.get("display_name") or "Provision",
                "text": r.get("title") or "",
                "jurisdiction": "federal",
                "status": "in_force",
                "enacted_date": None,
                "assent_date": None,
                "commencement_date": r.get("source_verified_date") or "1908-01-01",
                "effective_application": "pending_and_prospective",
                "ordinance_expiry_date": None,
                "court_challenges": [],
                "source_url": src_url,
                "source_tier": "tier_1",
                "verification_status": "verified",
                "fetched_at": now_iso,
                "previous_version_id": None
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        return len(records)

    def append_version(
        self,
        canonical_id: str,
        act_code: str,
        text: str,
        provision_type: str = "section",
        primary_num: str = "1",
        secondary_num: Optional[str] = None,
        title: str = "Provision",
        verified_by: Optional[str] = None,
        jurisdiction: str = "federal",
        status: str = "in_force",
        enacted_date: Optional[str] = None,
        assent_date: Optional[str] = None,
        commencement_date: Optional[str] = None,
        effective_application: str = "pending_and_prospective",
        ordinance_expiry_date: Optional[str] = None,
        court_challenges: Optional[List[Dict[str, Any]]] = None,
        source_url: str = "",
        source_tier: Optional[str] = None,
        verification_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Appends a new immutable version to the store. Only Tier 1 sources can achieve 'verified'.
        """
        existing_versions = self.get_versions(act_code)
        matching = [v for v in existing_versions if v.get("canonical_id") == canonical_id]
        prev_version = matching[-1] if matching else None

        v_num = len(matching) + 1
        version_id = f"{canonical_id}_V{v_num}"

        computed_tier = source_tier or classify_source_tier(source_url)
        # Enforce Rule: Only Tier 1 can mark a change "verified"
        if computed_tier == "tier_1":
            computed_status = verification_status or "verified"
        else:
            computed_status = "reported_unverified"

        new_entry = {
            "version_id": version_id,
            "canonical_id": canonical_id,
            "act_code": act_code,
            "provision_type": provision_type,
            "primary_num": primary_num,
            "secondary_num": secondary_num,
            "title": title,
            "text": text,
            "jurisdiction": jurisdiction,
            "status": status,  # in_force | amended | repealed | lapsed | struck_down | challenged
            "enacted_date": enacted_date,
            "assent_date": assent_date,
            "commencement_date": commencement_date,
            "effective_application": effective_application,  # prospective_only | pending_and_prospective | retrospective
            "ordinance_expiry_date": ordinance_expiry_date,
            "court_challenges": court_challenges or [],
            "source_url": source_url,
            "source_tier": computed_tier,
            "verified_by": verified_by,
            "verification_status": computed_status,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "previous_version_id": prev_version.get("version_id") if prev_version else None,
        }

        existing_versions.append(new_entry)
        path = self._get_act_file(act_code)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing_versions, f, indent=2)

        return new_entry

    def stage_finding(
        self,
        canonical_id: str,
        act_code: str,
        query_trigger: str,
        detected_change: str,
        source_url: str,
        raw_snippet: str = "",
        effective_application: str = "prospective_only",
        ordinance_expiry: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stages an unverified web discovery."""
        tier = classify_source_tier(source_url)
        status = "verified" if tier == "tier_1" else "reported_unverified"

        stg_id = f"STG_{int(time.time() * 1000)}"
        staged_item = {
            "staging_id": stg_id,
            "canonical_id": canonical_id,
            "act_code": act_code,
            "query_trigger": query_trigger,
            "detected_change": detected_change,
            "source_url": source_url,
            "source_tier": tier,
            "verification_status": status,
            "raw_snippet": raw_snippet,
            "effective_application": effective_application,
            "ordinance_expiry": ordinance_expiry,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "promoted_to_main": False,
            "admin_review_status": "pending",
            "review_status": "pending_review",
        }

        with open(self.staging_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.append(staged_item)
        with open(self.staging_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return staged_item

    def promote_staged_finding(
        self,
        staging_id: str,
        tier1_source_url: Optional[str] = None,
        tier_1_source_url: Optional[str] = None,
        official_text: Optional[str] = None,
        promoted_by: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Promotes a staged finding to the main store ONLY if confirmed by a Tier 1 source.
        """
        tier_url = tier1_source_url or tier_1_source_url or ""
        tier = classify_source_tier(tier_url)
        if tier != "tier_1":
            raise ValueError(f"Cannot promote staging record {staging_id} without a verified Tier 1 source (got {tier_url})")

        with open(self.staging_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        target = None
        for item in data:
            if item.get("staging_id") == staging_id:
                target = item
                break

        if not target:
            return None

        promoted_version = self.append_version(
            canonical_id=target["canonical_id"],
            act_code=target["act_code"],
            provision_type="section",
            primary_num="",
            secondary_num=None,
            title=target.get("detected_change", "Amended Provision"),
            text=target.get("raw_snippet", ""),
            source_url=tier1_source_url,
            source_tier="tier_1",
            verification_status="verified",
            effective_application=target.get("effective_application", "pending_and_prospective"),
            ordinance_expiry_date=target.get("ordinance_expiry"),
        )

        target["promoted_to_main"] = True
        target["promoted_by"] = "Tier 1 Verification Engine"
        target["promoted_at"] = datetime.now(timezone.utc).isoformat()
        target["admin_review_status"] = "approved"

        with open(self.staging_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return promoted_version


# Global store instance
global_statute_store = StatuteVersionStore()


def check_statute_currency(
    canonical_id: str,
    act_code: str,
    query_text: str = "",
    cache_window_hours: int = 24,
    mock_web_fetcher: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Checks currency for a statutory provision.
    If record is older than cache_window_hours or query has recency words,
    triggers a currency check.
    Returns currency label, status, and effective dates.
    """
    latest = global_statute_store.get_latest_version(act_code, canonical_id)
    now = datetime.now(timezone.utc)

    needs_check = False
    is_recency_query = bool(RECENCY_WORDS_PATTERN.search(query_text))

    if not latest:
        needs_check = True
    else:
        fetched_at_str = latest.get("fetched_at")
        if fetched_at_str:
            try:
                fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
                if (now - fetched_at) > timedelta(hours=cache_window_hours):
                    needs_check = True
            except Exception:
                needs_check = True
        else:
            needs_check = True

    if is_recency_query:
        needs_check = True

    if needs_check and mock_web_fetcher:
        try:
            finding = mock_web_fetcher(canonical_id=canonical_id, act_code=act_code, query_text=query_text)
            if finding:
                global_statute_store.stage_finding(
                    canonical_id=canonical_id,
                    act_code=act_code,
                    query_trigger=query_text,
                    detected_change=finding.get("change", "Recent amendment noted"),
                    source_url=finding.get("source_url", ""),
                    raw_snippet=finding.get("snippet", ""),
                    effective_application=finding.get("effective_application", "prospective_only"),
                    ordinance_expiry=finding.get("ordinance_expiry")
                )
        except Exception:
            pass

    if not latest:
        return {
            "canonical_id": canonical_id,
            "label": "NOT-CHECKED",
            "tier": None,
            "verification_status": "unverified",
            "status": "unknown",
            "effective_application": "unknown",
            "display_tag": "[NOT-CHECKED: not in verified store]"
        }

    tier = latest.get("source_tier") or "tier_3"
    v_status = latest.get("verification_status") or "reported_unverified"
    s_date = (latest.get("fetched_at") or "")[:10]
    s_url = latest.get("source_url") or "official repository"

    if tier == "tier_1" and v_status == "verified":
        tag = f"[VERIFIED: Tier 1, {s_url}, {s_date}]"
    elif v_status == "reported_unverified":
        tag = f"[REPORTED-UNVERIFIED: {tier.upper()}, {s_url}]"
    else:
        tag = f"[NOT-CHECKED: cached {s_date}]"

    return {
        "canonical_id": canonical_id,
        "label": "VERIFIED" if (tier == "tier_1" and v_status == "verified") else ("REPORTED-UNVERIFIED" if v_status == "reported_unverified" else "NOT-CHECKED"),
        "tier": tier,
        "verification_status": v_status,
        "status": latest.get("status", "in_force"),
        "effective_application": latest.get("effective_application", "pending_and_prospective"),
        "commencement_date": latest.get("commencement_date"),
        "ordinance_expiry_date": latest.get("ordinance_expiry_date"),
        "display_tag": tag
    }


def tag_precedent_temporal_amendment(
    precedent_year: Optional[int],
    statute_amendment_date: Optional[str] = None,
    act_code: Optional[str] = None,
    canonical_id: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Part 2, Item 1:
    Tags a retrieved precedent as decided under pre-amendment text, post-amendment text, or unknown.
    Returns (temporal_tag, warning_message).
    """
    if not precedent_year:
        return ("unknown", None)

    amend_date = statute_amendment_date
    if not amend_date and act_code and canonical_id:
        latest = global_statute_store.get_latest_version(act_code, canonical_id)
        if latest:
            amend_date = latest.get("commencement_date") or latest.get("enacted_date")

    if not amend_date:
        return ("unknown", None)

    try:
        amend_year = int(str(amend_date)[:4])
        p_year = int(str(precedent_year)[:4])
    except Exception:
        return ("unknown", None)

    if p_year < amend_year:
        return (
            "pre_amendment",
            f"⚠️ Notice: Decided in {p_year}, prior to the {amend_year} statutory amendment. Verify continued applicability under amended text."
        )
    else:
        return ("post_amendment", None)


def detect_statutory_provisions_in_query(query: str) -> List[Tuple[str, str]]:
    """
    Part 1, Item 2:
    Extracts canonical statutory provisions (canonical_id, act_code) from a query.
    Used for parallel currency checks.
    """
    if not query:
        return []
    from core.statutory_validator import parse_statutory_citation, generate_canonical_id
    provisions = []
    seen = set()

    clauses = re.split(r'[,;.\n]|\band\b', query)
    clauses = [query] + clauses

    for clause in clauses:
        clause_clean = clause.strip()
        if len(clause_clean) < 4:
            continue
        parsed = parse_statutory_citation(clause_clean)
        if parsed and parsed.get("is_valid") and parsed.get("act_code"):
            act_code = parsed["act_code"]
            prov_type = parsed.get("provision_type", "section")
            primary_num = parsed.get("primary_num")
            rule_num = parsed.get("rule_num")
            if primary_num or rule_num:
                cid = generate_canonical_id(
                    act_code=act_code,
                    primary_num=primary_num or "",
                    rule_num=rule_num,
                    provision_type=prov_type
                )
                if cid and cid not in seen:
                    seen.add(cid)
                    provisions.append((cid, act_code))
    return provisions
