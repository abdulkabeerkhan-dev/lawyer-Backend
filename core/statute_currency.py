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
import logging
import hashlib
import urllib.parse
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union

logger = logging.getLogger(__name__)

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTE_VERSIONS_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_versions")
STATUTE_STAGING_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_staging")
TABLES_DIR = os.path.join(WORKSPACE_DIR, "data", "statute_tables")

class StatuteStatus(str, Enum):
    BILL = "bill"
    PASSED = "passed"
    ASSENTED = "assented"
    NOTIFIED = "notified"
    COMMENCED = "commenced"
    IN_FORCE = "in_force"
    AMENDED = "amended"
    REPEALED = "repealed"
    LAPSED = "lapsed"
    OMITTED = "omitted"
    DECLARED_REPUGNANT_APPEAL_PENDING = "declared_repugnant_appeal_pending"
    STRUCK_DOWN = "struck_down"

VALID_STATUSES = {s.value for s in StatuteStatus}

# Only assented, notified, commenced, in_force, and amended count as law.
# A bill or a "passed" item is never described as law.
LAW_STATUSES = {
    StatuteStatus.ASSENTED.value,
    StatuteStatus.NOTIFIED.value,
    StatuteStatus.COMMENCED.value,
    StatuteStatus.IN_FORCE.value,
    StatuteStatus.AMENDED.value,
}

def is_law_status(status: Optional[str]) -> bool:
    """
    Returns True only if the status qualifies as law.
    Only assented, notified, commenced, in_force, and amended count as law.
    A bill or a 'passed' item is never described as law.
    """
    if not status:
        return False
    return str(status).strip().lower() in LAW_STATUSES

VALID_JURISDICTIONS = {
    "federal",
    "punjab",
    "sindh",
    "kp",
    "kpk",
    "balochistan",
}

os.makedirs(STATUTE_VERSIONS_DIR, exist_ok=True)
os.makedirs(STATUTE_STAGING_DIR, exist_ok=True)

from core.domain_whitelist import ALL_TIER_1_DOMAINS, extract_hostname

# TIER 1: Official government, parliament, gazette, and court portals (from core.domain_whitelist)
TIER_1_DOMAINS = sorted(list(ALL_TIER_1_DOMAINS))

# TIER 2: Established, reputable legal reporting journals/portals
TIER_2_DOMAINS = [
    "pakistanlawsite.com",
    "pljlawsite.com",
    "courtingthelaw.com",
    "manzoorlaw.com",
]

RECENCY_WORDS_PATTERN = re.compile(
    r"\b(new|recent|recently|amended|amendment|latest|updated|ordinance)\b",
    re.IGNORECASE
)


def classify_source_tier(source_url: str) -> str:
    """
    Classifies a URL into Tier 1 (official), Tier 2 (reputable legal), or Tier 3 (news/blogs).
    Strictly parses the hostname/netloc to prevent URL spoofing (e.g., evil.com/?ref=na.gov.pk
    or na.gov.pk.evil.com or blog.com/pakistancode.gov.pk).
    """
    if not source_url:
        return "tier_3"
    try:
        netloc = extract_hostname(source_url)
        if not netloc:
            return "tier_3"
        for d in TIER_1_DOMAINS:
            if netloc == d or netloc.endswith("." + d):
                return "tier_1"
        for d in TIER_2_DOMAINS:
            if netloc == d or netloc.endswith("." + d):
                return "tier_2"
    except Exception:
        pass
    return "tier_3"


def _version_sort_key(version: Dict[str, Any]) -> int:
    """Extracts numeric version number for ordering (e.g. V10 > V2)."""
    vid = str(version.get("version_id", ""))
    m = re.search(r'_V(\d+)$', vid, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


class StatuteVersionStore:
    """
    Immutable versioned store for statutory sections.
    Never overwrites existing records; always appends a new version referencing previous_version_id.
    """

    def __init__(self, storage_dir: str = STATUTE_VERSIONS_DIR, staging_dir: str = STATUTE_STAGING_DIR, supabase_client: Optional[Any] = None):
        self.storage_dir = storage_dir
        self.staging_dir = staging_dir
        self.staging_file = os.path.join(staging_dir, "statute_currency_staging.json")
        self._ensure_staging_file()
        if supabase_client is False:
            self.supabase = None
        elif supabase_client is not None:
            self.supabase = supabase_client
        elif self.storage_dir != STATUTE_VERSIONS_DIR:
            # Custom storage directory (e.g. unit tests / hermetic runs) should not hit remote DB
            self.supabase = None
        else:
            self.supabase = None
            sb_url = os.environ.get("SUPABASE_URL")
            sb_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
            if sb_url and sb_key:
                try:
                    from supabase import create_client
                    self.supabase = create_client(sb_url, sb_key)
                except Exception:
                    self.supabase = None

    def _ensure_staging_file(self):
        if not os.path.exists(self.staging_file):
            with open(self.staging_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def _get_act_file(self, act_code: str) -> str:
        clean_act = re.sub(r"[^A-Za-z0-9_]+", "", act_code.upper())
        return os.path.join(self.storage_dir, f"{clean_act}_versions.json")

    def get_versions(self, act_code: str) -> List[Dict[str, Any]]:
        clean_act = act_code.upper()
        if self.supabase:
            try:
                res = self.supabase.table("statute_versions").select("*").eq("act_code", clean_act).order("version_id").execute()
                if res and res.data:
                    return res.data
            except Exception as e:
                logger.debug(f"Supabase statute_versions query notice: {e}")

        path = self._get_act_file(act_code)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def get_latest_version(self, act_code: str, canonical_id: str) -> Optional[Dict[str, Any]]:
        """Returns the latest version ordered numerically by version number (_V1, _V2, _V10)."""
        if self.supabase:
            try:
                res = self.supabase.table("statute_versions").select("*").eq("canonical_id", canonical_id).execute()
                if res and res.data:
                    return max(res.data, key=_version_sort_key)
            except Exception as e:
                logger.debug(f"Supabase statute_versions latest query notice: {e}")

        versions = self.get_versions(act_code)
        matching = [v for v in versions if v.get("canonical_id") == canonical_id]
        if not matching:
            return None
        return max(matching, key=_version_sort_key)

    def batch_import_initial_versions(self, act_code: str, provisions: List[Dict[str, Any]]) -> int:
        """Batch-imports initial provisions with truthful baseline_unverified status."""
        path = self._get_act_file(act_code)
        if os.path.exists(path) and os.path.getsize(path) > 10:
            return 0
        records = []
        clean_act = act_code.upper()
        default_jurisdiction = "punjab" if clean_act in ("PRPA_2009", "PREEMPTION_1991") else "federal"
        for r in provisions:
            cid = r.get("canonical_id")
            if not cid:
                continue
            title = r.get("title") or r.get("display_name") or "Provision"
            records.append({
                "version_id": f"{cid}_V1",
                "canonical_id": cid,
                "act_code": act_code,
                "provision_type": r.get("provision_type", "section"),
                "primary_num": str(r.get("primary_num") or ""),
                "secondary_num": r.get("secondary_num"),
                "title": title,
                "title_only": title,
                "text": None,
                "text_available": False,
                "jurisdiction": r.get("jurisdiction", default_jurisdiction),
                "status": "in_force",
                "enacted_date": None,
                "assent_date": None,
                "commencement_date": None,
                "valid_from": None,
                "valid_to": None,
                "amending_instrument": None,
                "gazette_reference": None,
                "effective_application": "pending_and_prospective",
                "ordinance_expiry_date": None,
                "court_challenges": [],
                "source_url": None,
                "source_tier": None,
                "verification_status": "baseline_unverified",
                "fetched_at": None,
                "previous_version_id": None
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        if self.supabase:
            try:
                self.supabase.table("statute_versions").upsert(records, on_conflict="version_id").execute()
            except Exception as e:
                logger.debug(f"Supabase statute_versions batch upsert notice: {e}")
        return len(records)

    def append_version(
        self,
        canonical_id: str,
        act_code: str,
        text: Optional[str] = None,
        title_only: Optional[str] = None,
        provision_type: str = "section",
        primary_num: str = "1",
        secondary_num: Optional[str] = None,
        title: str = "Provision",
        verified_by: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        sources_checked: Optional[List[str]] = None,
        jurisdiction: str = "federal",
        status: str = "in_force",
        enacted_date: Optional[str] = None,
        assent_date: Optional[str] = None,
        commencement_date: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        amending_instrument: Optional[str] = None,
        gazette_reference: Optional[str] = None,
        effective_application: str = "pending_and_prospective",
        ordinance_expiry_date: Optional[str] = None,
        court_challenges: Optional[List[Dict[str, Any]]] = None,
        source_url: Optional[str] = None,
        source_tier: Optional[str] = None,
        verification_status: Optional[str] = None,
        text_available: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Appends a new immutable version to the store.
        change_confirmed strictly requires human reviewer_name and sources_checked.
        Validates status against StatuteStatus enum and jurisdiction against VALID_JURISDICTIONS.
        """
        status_clean = str(status).strip().lower()
        if status_clean not in VALID_STATUSES:
            raise ValueError(f"Unknown statute status: '{status}'. Must be one of: {sorted(list(VALID_STATUSES))}")

        jurisdiction_clean = str(jurisdiction).strip().lower()
        if jurisdiction_clean not in VALID_JURISDICTIONS:
            raise ValueError(f"Unknown jurisdiction: '{jurisdiction}'. Must be one of: {sorted(list(VALID_JURISDICTIONS))}")

        existing_versions = self.get_versions(act_code)
        matching = [v for v in existing_versions if v.get("canonical_id") == canonical_id]
        prev_version = matching[-1] if matching else None

        v_num = len(matching) + 1
        version_id = f"{canonical_id}_V{v_num}"

        computed_tier = source_tier if source_tier is not None else (classify_source_tier(source_url) if source_url else None)
        active_reviewer = reviewer_name or verified_by
        active_sources = sources_checked or []

        # Enforce Rule: Only Tier 1 with named human reviewer can achieve verified/change_confirmed
        if verification_status in ("change_confirmed", "verified"):
            if active_reviewer and computed_tier == "tier_1":
                computed_status = verification_status
            else:
                computed_status = "reported_unverified"
        elif computed_tier == "tier_1":
            computed_status = verification_status or ("verified" if active_reviewer else "reported_unverified")
        elif computed_tier:
            computed_status = "reported_unverified"
        else:
            computed_status = verification_status or "baseline_unverified"

        has_text = bool(text) if text_available is None else bool(text_available)

        new_entry = {
            "version_id": version_id,
            "canonical_id": canonical_id,
            "act_code": act_code,
            "provision_type": provision_type,
            "primary_num": primary_num,
            "secondary_num": secondary_num,
            "title": title,
            "title_only": title_only or title,
            "text": text if has_text else None,
            "text_available": has_text,
            "jurisdiction": jurisdiction_clean,
            "status": status_clean,
            "enacted_date": enacted_date,
            "assent_date": assent_date,
            "commencement_date": commencement_date,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "amending_instrument": amending_instrument,
            "gazette_reference": gazette_reference,
            "effective_application": effective_application,
            "ordinance_expiry_date": ordinance_expiry_date,
            "court_challenges": court_challenges or [],
            "source_url": source_url,
            "source_tier": computed_tier,
            "verified_by": active_reviewer,
            "reviewer_name": active_reviewer,
            "sources_checked": active_sources,
            "verification_status": computed_status,
            "fetched_at": datetime.now(timezone.utc).isoformat() if computed_tier else None,
            "previous_version_id": prev_version.get("version_id") if prev_version else None,
        }

        existing_versions.append(new_entry)
        path = self._get_act_file(act_code)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing_versions, f, indent=2)

        if self.supabase:
            try:
                valid_cols = {
                    'version_id', 'canonical_id', 'act_code', 'provision_type', 'primary_num',
                    'secondary_num', 'title', 'title_only', 'text', 'text_available', 'jurisdiction',
                    'status', 'enacted_date', 'assent_date', 'commencement_date', 'valid_from',
                    'valid_to', 'amending_instrument', 'gazette_reference', 'effective_application',
                    'ordinance_expiry_date', 'court_challenges', 'source_url', 'source_tier',
                    'verification_status', 'fetched_at', 'previous_version_id'
                }
                sb_payload = {k: new_entry[k] for k in new_entry if k in valid_cols}
                self.supabase.table("statute_versions").insert(sb_payload).execute()
            except Exception as e:
                logger.debug(f"Supabase statute_versions insert notice: {e}")

        return new_entry

    def stage_finding(
        self,
        canonical_id: str,
        act_code: str,
        query_trigger: str,
        detected_change: str,
        source_url: str,
        raw_snippet: str = "",
        effective_application: str = "pending_and_prospective",
        ordinance_expiry: Optional[str] = None,
        signal_term: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Stages an unverified web discovery.
        Status is ALWAYS 'pending_review' (never 'verified' - automated fetchers cannot verify).
        Hashes query_trigger to prevent leaking client facts.
        """
        tier = classify_source_tier(source_url)
        # Enforce Rule: An automated staged finding is NEVER verified, even from Tier 1!
        status = "pending_review"

        # Hash query trigger to avoid storing raw client facts
        query_hash = hashlib.sha256((query_trigger or "").encode("utf-8")).hexdigest()[:16]

        stg_id = f"STG_{int(time.time() * 1000)}"
        staged_item = {
            "staging_id": stg_id,
            "canonical_id": canonical_id,
            "act_code": act_code,
            "query_hash": query_hash,
            "detected_change": detected_change,
            "source_url": source_url,
            "source_tier": tier,
            "verification_status": status,
            "raw_snippet": raw_snippet,
            "signal_term": signal_term,
            "effective_application": effective_application,
            "ordinance_expiry": ordinance_expiry,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "promoted_to_main": False,
            "admin_review_status": "pending",
            "review_status": "pending_review",
            "reviewer_name": None,
            "sources_checked": []
        }

        with open(self.staging_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.append(staged_item)
        with open(self.staging_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return staged_item

    def get_staged_findings(self, canonical_id: Optional[str] = None, act_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns unpromoted staged findings matching canonical_id or act_code."""
        if not os.path.exists(self.staging_file):
            return []
        try:
            with open(self.staging_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            matching = []
            for item in data:
                if item.get("promoted_to_main"):
                    continue
                if canonical_id and item.get("canonical_id") == canonical_id:
                    matching.append(item)
                elif act_code and item.get("act_code") == act_code:
                    matching.append(item)
            return matching
        except Exception:
            return []

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
            text=official_text or target.get("raw_snippet", ""),
            source_url=tier_url,
            source_tier="tier_1",
            verified_by=promoted_by or "Senior Reviewer",
            reviewer_name=promoted_by or "Senior Reviewer",
            sources_checked=[tier_url],
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


# Baseline acts with official ground-truth bare-act tables in data/statute_tables
SUPPORTED_STATUTE_TABLES = {
    "CNSA_1997", "CONST_1973", "CPC_1908", "CRPC_1898", "DMMA_1939",
    "FAMILY_COURTS_1964", "FIO_2001", "LIMITATION_1908", "MFLO_1961",
    "PPC_1860", "PREEMPTION_1991", "PRPA_2009", "QSO_1984"
}


def check_statute_currency(
    canonical_id: str,
    act_code: str,
    query_text: str = "",
    cache_window_hours: int = 24,
    mock_web_fetcher: Optional[Any] = None,
    online_checked: Optional[bool] = None,
    online_sources: Optional[str] = None,
    online_check_date: Optional[str] = None,
    search_outcome: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks currency for a statutory provision.
    If record is older than cache_window_hours or query has recency words,
    triggers a currency check.
    Returns currency label, status, and effective dates.
    """
    # If the statute itself is not in the official baseline bare-act tables:
    if act_code not in SUPPORTED_STATUTE_TABLES:
        if os.environ.get("STATUTE_CURRENCY_LABELS", "").strip().lower() == "off":
            display_tag = ""
        else:
            display_tag = "[NOT CHECKED: statute not in tables]"
        return {
            "canonical_id": canonical_id,
            "act_code": act_code,
            "label": "NOT CHECKED",
            "tier": None,
            "verification_status": "statute_not_in_tables",
            "status": "not_in_tables",
            "effective_application": "unknown",
            "commencement_date": None,
            "ordinance_expiry_date": None,
            "title_only": None,
            "text_available": False,
            "jurisdiction": "federal",
            "valid_from": None,
            "valid_to": None,
            "amending_instrument": None,
            "gazette_reference": None,
            "court_challenges": [],
            "display_tag": display_tag
        }

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
                    effective_application=finding.get("effective_application", "pending_and_prospective"),
                    ordinance_expiry=finding.get("ordinance_expiry")
                )
        except Exception:
            pass

    if not latest:
        if os.environ.get("STATUTE_CURRENCY_LABELS", "").strip().lower() == "off":
            display_tag = ""
        elif search_outcome in ("no_pages_returned", "search_failed", "still_running"):
            outcome_msg = search_outcome.replace("_", " ")
            display_tag = f"[NOT CHECKED: {outcome_msg}]"
        else:
            display_tag = "[NOT CHECKED]"
        return {
            "canonical_id": canonical_id,
            "act_code": act_code,
            "label": "NOT CHECKED",
            "tier": None,
            "verification_status": "unverified",
            "status": "unknown",
            "effective_application": "unknown",
            "commencement_date": None,
            "ordinance_expiry_date": None,
            "title_only": None,
            "text_available": False,
            "jurisdiction": "federal",
            "valid_from": None,
            "valid_to": None,
            "amending_instrument": None,
            "gazette_reference": None,
            "court_challenges": [],
            "display_tag": display_tag
        }

    is_online_checked = bool(online_checked) if online_checked is not None else bool(latest.get("online_checked", False))
    tier = latest.get("source_tier")
    v_status = latest.get("verification_status") or "baseline_unverified"
    s_date = (latest.get("fetched_at") or "")[:10]
    s_url = latest.get("source_url") or "official repository"
    status_val = str(latest.get("status", "")).strip().lower()

    # Part 1, Item 4: Strict Display Tags:
    # 1. [CHANGE CONFIRMED]
    # 2. [CHECKED, NO CHANGE FOUND: <source> on <date>] or [CHECKED, NO CHANGE FOUND]
    # 3. [CHANGE FOUND, PENDING REVIEW]
    # 4. [REPORTED, UNVERIFIED]
    # 5. [BILL PENDING]
    # 6. [NOT CHECKED: ...] / [NOT CHECKED]
    # 7. [BASELINE TABLE: not checked online]
    # NEVER use "verified" or "current"!
    if os.environ.get("STATUTE_CURRENCY_LABELS", "").strip().lower() == "off":
        tag = ""
        label = "DISABLED"
    elif search_outcome in ("no_pages_returned", "search_failed", "still_running"):
        outcome_msg = search_outcome.replace("_", " ")
        tag = f"[NOT CHECKED: {outcome_msg}]"
        label = "NOT CHECKED"
    elif status_val in ("bill", "passed"):
        tag = "[BILL PENDING]"
        label = "BILL PENDING"
    else:
        # Check if there is an unpromoted staged finding for this provision or act
        staged_items = global_statute_store.get_staged_findings(canonical_id=canonical_id, act_code=act_code)
        if staged_items:
            latest_staged = staged_items[-1]
            if latest_staged.get("source_tier") == "tier_1":
                tag = "[CHANGE FOUND, PENDING REVIEW]"
                label = "CHANGE FOUND, PENDING REVIEW"
            else:
                tag = "[REPORTED, UNVERIFIED]"
                label = "REPORTED, UNVERIFIED"
        elif v_status == "reported_unverified":
            tag = "[REPORTED, UNVERIFIED]"
            label = "REPORTED, UNVERIFIED"
        elif v_status == "change_confirmed" or (v_status == "verified" and latest.get("reviewer_name") and latest.get("sources_checked")):
            tag = "[CHANGE CONFIRMED]"
            label = "CHANGE CONFIRMED"
        elif is_online_checked:
            if online_sources or online_check_date:
                src = online_sources or "Pakistan Code, National Assembly"
                dt = online_check_date or s_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
                tag = f"[CHECKED, NO CHANGE FOUND: {src} on {dt}]"
            else:
                tag = "[CHECKED, NO CHANGE FOUND]"
            label = "CHECKED, NO CHANGE FOUND"
        elif v_status == "baseline_unverified":
            tag = "[BASELINE TABLE: not checked online]"
            label = "BASELINE"
        else:
            tag = "[NOT CHECKED]"
            label = "NOT CHECKED"

    return {
        "canonical_id": canonical_id,
        "act_code": act_code,
        "label": label,
        "tier": tier,
        "verification_status": v_status,
        "status": latest.get("status", "in_force"),
        "effective_application": latest.get("effective_application", "pending_and_prospective"),
        "commencement_date": latest.get("commencement_date"),
        "ordinance_expiry_date": latest.get("ordinance_expiry_date"),
        "title_only": latest.get("title_only") or latest.get("title"),
        "text_available": bool(latest.get("text_available", False)),
        "jurisdiction": latest.get("jurisdiction", "federal"),
        "valid_from": latest.get("valid_from"),
        "valid_to": latest.get("valid_to"),
        "amending_instrument": latest.get("amending_instrument"),
        "gazette_reference": latest.get("gazette_reference"),
        "court_challenges": latest.get("court_challenges", []),
        "display_tag": tag
    }


def tag_precedent_temporal_amendment(
    precedent_year: Optional[Union[int, str]],
    statute_amendment_date: Optional[str] = None,
    act_code: Optional[str] = None,
    canonical_id: Optional[str] = None,
    amending_instrument: Optional[str] = None,
    section_label: Optional[str] = None,
    store: Optional[StatuteVersionStore] = None
) -> Tuple[str, Optional[str]]:
    """
    Part 1, Item 2: Temporal Tagging
    Tags a retrieved precedent as decided under pre-amendment text, post-amendment text, or unknown.
    Returns (temporal_tag, warning_message).

    STRICT RULES:
    1. Returns 'unknown' unless the provision has a REAL amendment record
       (amending_instrument present AND valid_from set).
    2. Neutral warning wording:
       "Decided before the <date> amendment of <section>. Check whether the amendment affects this point."
    3. NEVER says "interprets repealed language" or alarmist language.
    """
    if not precedent_year:
        return ("unknown", None)

    # 1. Resolve real amendment record
    active_store = store or global_statute_store
    amend_date = statute_amendment_date
    inst = amending_instrument

    # If act_code and canonical_id provided, look in version store for real amendment records
    if act_code and canonical_id:
        versions = active_store.get_versions(act_code)
        matching = [v for v in versions if v.get("canonical_id") == canonical_id]
        # An amendment record is a version that has an amending_instrument AND valid_from
        amendment_versions = [
            v for v in matching
            if v.get("amending_instrument") and v.get("valid_from")
        ]
        if amendment_versions:
            latest_amend = amendment_versions[-1]
            if not amend_date:
                amend_date = latest_amend.get("valid_from")
            if not inst:
                inst = latest_amend.get("amending_instrument")
            if not section_label:
                section_label = latest_amend.get("title_only") or latest_amend.get("title")

    # If still missing either amending_instrument or valid_from (amend_date), we cannot confirm a real amendment
    if not inst or not amend_date:
        return ("unknown", None)

    # 2. Extract precedent year and amendment year/date
    try:
        p_str = str(precedent_year).strip()
        m_py = re.search(r'\b(19\d\d|20\d\d)\b', p_str)
        if not m_py:
            return ("unknown", None)
        p_year = int(m_py.group(1))

        amend_date_str = str(amend_date).strip()
        m_ay = re.search(r'\b(19\d\d|20\d\d)\b', amend_date_str)
        if not m_ay:
            return ("unknown", None)
        amend_year = int(m_ay.group(1))
    except Exception:
        return ("unknown", None)

    # 3. Resolve section display label
    if not section_label:
        if canonical_id:
            m = re.search(r'_(SEC|ART|RULE|SECTION)_([A-Za-z0-9_\-]+)$', canonical_id, re.IGNORECASE)
            if m:
                ptype = "Section" if m.group(1).upper() in ("SEC", "SECTION") else ("Article" if m.group(1).upper() == "ART" else "Rule")
                sec_num = m.group(2).replace('_', '-')
                section_label = f"{ptype} {sec_num}"
            else:
                section_label = canonical_id
        else:
            section_label = "the provision"

    # 4. Compare dates
    # If both full ISO dates YYYY-MM-DD are present, perform date comparison
    if len(p_str) >= 10 and len(amend_date_str) >= 10 and re.match(r'^\d{4}-\d{2}-\d{2}', p_str) and re.match(r'^\d{4}-\d{2}-\d{2}', amend_date_str):
        is_pre = p_str[:10] < amend_date_str[:10]
    else:
        is_pre = p_year < amend_year

    if is_pre:
        warning_msg = f"Decided before the {amend_date_str} amendment of {section_label}. Check whether the amendment affects this point."
        return ("pre_amendment", warning_msg)
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
    from core.statutory_validator import parse_statutory_citation, generate_canonical_id, ACT_ALIASES
    provisions = []
    seen = set()

    # Detect any explicitly mentioned act in the whole query to establish primary context
    query_lower = query.lower()
    context_act_code = None
    for alias, code in sorted(ACT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf'\b{re.escape(alias)}\b', query_lower):
            context_act_code = code
            break

    if not context_act_code:
        m_dyn = re.search(
            r'\b(?:of\s+(?:the\s+)?)([a-z\s]+(?:act|ordinance|code|order))(?:\s*,\s*(\d{4}))?\b',
            query_lower
        )
        if m_dyn:
            raw_act_name = m_dyn.group(1).strip()
            act_yr = m_dyn.group(2)
            norm_name = re.sub(r'[^a-z0-9]+', '_', raw_act_name).strip('_').upper()
            context_act_code = f"{norm_name}_{act_yr}" if act_yr else norm_name

    clauses = re.split(r'[,;.\n]|\band\b', query)
    clauses = [query] + clauses

    for clause in clauses:
        clause_clean = clause.strip()
        if len(clause_clean) < 4:
            continue
        parsed = parse_statutory_citation(clause_clean)
        if parsed and parsed.get("is_valid"):
            act_code = parsed.get("act_code") or context_act_code
            if not act_code:
                continue
            prov_type = parsed.get("provision_type", "section")
            primary_num = parsed.get("primary_num")
            rule_num = parsed.get("rule_num")

            # CPC substantive sections only go up to 158
            if act_code == "CPC_1908" and prov_type == "section" and primary_num and primary_num.isdigit() and int(primary_num) > 158:
                continue

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
