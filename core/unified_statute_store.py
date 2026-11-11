"""
core/unified_statute_store.py

Single authoritative source-of-truth lookup API for Pakistani statutes.
Merges statute tables and versions into a unified in-memory and disk registry.
Every provision returns:
- act_code, act_name
- primary_num, canonical_id, title
- verbatim text (or explicit missing_reason)
- source_file, source_page, content_hash
- tier ('ingested_unreviewed' / 'reviewed' / 'disputed')
- status ('in_force' / 'repealed' / 'omitted')
- jurisdiction ('federal' / province)
- effective_from, effective_to
"""

import os
import json
import re
from typing import Dict, List, Any, Optional

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIFIED_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")
TABLES_DIR = os.path.join(REPO_DIR, "data", "statute_tables")
VERSIONS_DIR = os.path.join(REPO_DIR, "data", "statute_versions")
REVIEWS_DIR = os.path.join(REPO_DIR, "data", "reviews")

def review_file_present(canonical_id: str, content_hash: str) -> bool:
    """
    Order 1.14 - Item 6: Checks presence of review metadata file on disk.
    This was previously called verify_reviewed_tier but only checked disk presence.
    """
    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    if not os.path.exists(review_file):
        return False
    try:
        import json
        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        return (
            str(data.get("canonical_id")).upper() == str(canonical_id).upper() and
            bool(data.get("reviewer_name")) and
            bool(data.get("review_date")) and
            str(data.get("record_content_hash")) == str(content_hash) and
            data.get("status") == "approved" and
            bool(data.get("cryptographic_signature"))
        )
    except Exception:
        return False

def verify_reviewed_tier(canonical_id: str, content_hash: str) -> bool:
    """
    Order 2.0 - Step 8: Cryptographic public-key signature verification for 'reviewed' tier with key pinning.
    The expected SHA-256 of the advocate public key must be supplied via ADVOCATE_PUBKEY_SHA256 env var.
    If unset or mismatched against data/reviews/advocate_public_key.pem, fails closed (returns False).
    """
    expected_pubkey_hash = os.environ.get("ADVOCATE_PUBKEY_SHA256")
    if not expected_pubkey_hash:
        return False

    review_file = os.path.join(REVIEWS_DIR, f"{canonical_id}.review.json")
    pub_key_file = os.path.join(REVIEWS_DIR, "advocate_public_key.pem")
    
    if not os.path.exists(review_file) or not os.path.exists(pub_key_file):
        return False
    try:
        with open(pub_key_file, "rb") as pf:
            pubkey_bytes = pf.read()

        import hashlib
        actual_pubkey_hash = hashlib.sha256(pubkey_bytes).hexdigest()
        if actual_pubkey_hash.lower() != expected_pubkey_hash.strip().lower():
            return False

        with open(review_file, "r", encoding="utf-8") as rf:
            data = json.load(rf)
        if str(data.get("canonical_id")).upper() != str(canonical_id).upper():
            return False
        if str(data.get("record_content_hash")) != str(content_hash):
            return False
        if data.get("status") != "approved":
            return False
        
        sig_hex = data.get("cryptographic_signature", "")
        if not sig_hex:
            return False
        sig_bytes = bytes.fromhex(sig_hex)

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        
        public_key = serialization.load_pem_public_key(pubkey_bytes)
        
        # Payload verified is canonical_id + content_hash
        payload = f"{canonical_id}:{content_hash}".encode("utf-8")
        
        public_key.verify(
            sig_bytes,
            payload,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False

class UnifiedStatuteStore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(UnifiedStatuteStore, cls).__new__(cls)
            cls._instance._loaded = False
            cls._instance._by_cid = {}
            cls._instance._by_act_num = {}
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self.load()

    def load(self):
        """Loads all unified statutes into fast in-memory hash maps."""
        self._by_cid.clear()
        self._by_act_num.clear()

        # Order 2.0 Step 1: App must load ONLY data/statutes_v2 from now on.
        target_dir = UNIFIED_DIR
        if not os.path.exists(target_dir):
            self._loaded = True
            return

        for fname in os.listdir(target_dir):
            if not fname.endswith(".json"):
                continue
            act_code = fname.replace(".json", "")
            fpath = os.path.join(target_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    provisions = json.load(f)
                    if isinstance(provisions, dict):
                        for k in ["sections", "provisions", "data"]:
                            if k in provisions and isinstance(provisions[k], list):
                                provisions = provisions[k]
                                break
                    if not isinstance(provisions, list):
                        continue
                    
                    for r in provisions:
                        if not isinstance(r, dict):
                            continue
                        cid = r.get("canonical_id")
                        num = str(r.get("primary_num") or "").strip()
                        act = str(r.get("act_code") or act_code).upper()

                        if not cid and num:
                            cid = f"{act}_SEC_{num}"

                        # Unit type normalization
                        if not r.get("provision_type"):
                            if "_ART_" in (cid or "") or "article" in str(r.get("section", "")).lower() or "CONST" in act:
                                r["provision_type"] = "article"
                            elif "_ORD_" in (cid or ""):
                                r["provision_type"] = "order"
                            elif "_RULE_" in (cid or ""):
                                r["provision_type"] = "rule"
                            else:
                                r["provision_type"] = "section"

                        # Backward compatibility alias for text_layer_matched <-> page_verified
                        if "text_layer_matched" in r:
                            r["page_verified"] = r.get("text_layer_matched")
                        elif "page_verified" in r:
                            r["text_layer_matched"] = r.get("page_verified")

                        if cid:
                            if r.get("tier") == "reviewed":
                                if not verify_reviewed_tier(cid.upper(), r.get("content_hash", "")):
                                    r["tier"] = "disputed" if r.get("is_disputed") else "ingested_unreviewed"
                            # Ensure text present from official gazette is quotable
                            if (
                                r.get("quoting_allowed") is not False
                                and (r.get("text") or r.get("text_raw"))
                                and r.get("tier") != "unsourced"
                            ):
                                r["quoting_allowed"] = True
                            self._by_cid[cid.upper()] = r
                        if num:
                            norm_num = re.sub(r'[^A-Z0-9]', '', num.upper())
                            expected_root_cids = {f"{act}_SEC_{norm_num}", f"{act}_ART_{norm_num}", f"{act}_ORD_{norm_num}"}
                            if (act, norm_num) not in self._by_act_num or cid in expected_root_cids:
                                self._by_act_num[(act, norm_num)] = r
                                self._by_act_num[(act, num.upper())] = r
            except Exception as e:
                pass

        self._loaded = True
        if not os.environ.get("SKIP_TURSO_DRIFT_CHECK"):
            self._verify_turso_drift_sample()

    def _verify_turso_drift_sample(self):
        """
        Compares 10 sampled canonical IDs in memory against Turso to alert on drift.
        Loudly logs an error if local JSON files and Turso have diverged.
        """
        sample_cids = [
            "LIMITATION_1908_ART_150",
            "PPC_1860_SEC_489F",
            "PPC_1860_SEC_302",
            "CRPC_1898_SEC_497",
            "CRPC_1898_SEC_498",
            "CRPC_1898_SEC_154",
            "CPC_1908_SEC_9",
            "CONTRACT_1872_SEC_73",
            "QSO_1984_ART_2",
            "CONST_1973_ART_199",
            "NI_ACT_1881_SEC_8",
            "NI_ACT_1881_SEC_31",
            "PPC_1860_SEC_51",
        ]
        try:
            from core.turso_client import get_statute_provision, is_turso_circuit_open
            if is_turso_circuit_open():
                return
            drifted = []
            for cid in sample_cids:
                local_rec = self._by_cid.get(cid)
                if not local_rec:
                    continue
                remote = get_statute_provision(cid)
                if not remote or not remote.get("verbatim_text"):
                    continue
                local_txt = (local_rec.get("text") or local_rec.get("verbatim_text") or "").strip()
                remote_txt = (remote.get("verbatim_text") or "").strip()
                if local_txt and remote_txt and local_txt != remote_txt:
                    drifted.append(cid)
            if drifted:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"CRITICAL DRIFT DETECTED: JSON files and Turso differ for {drifted}! "
                    "Run scripts/export_turso_to_json.py to synchronize."
                )
        except Exception:
            pass

    def get_by_canonical_id(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        if not self._loaded:
            self.load()
        if not canonical_id:
            return None
        cid_clean = canonical_id.strip().upper()

        # Limitation Act fused footnote normalization (e.g. 257 -> 57, 264 -> 64, 228 -> 28)
        if "LIMITATION" in cid_clean:
            fused_map = {
                "252": "52", "253": "53", "257": "57", "259": "59",
                "261": "61", "263": "63", "264": "64", "266": "66",
                "267": "67", "268": "68", "269": "69", "270": "70",
                "271": "71", "276": "76", "277": "77", "278": "78",
                "279": "79", "280": "80", "228": "28"
            }
            m_fused = re.search(r'_(?:ART|SEC)_([0-9]+)', cid_clean)
            if m_fused and m_fused.group(1) in fused_map:
                clean_num = fused_map[m_fused.group(1)]
                unit_str = "SEC" if (m_fused.group(1) == "228" or "_SEC_" in cid_clean) else "ART"
                return self.get_by_canonical_id(f"LIMITATION_1908_{unit_str}_{clean_num}")
        res = self._by_cid.get(cid_clean)
        if res:
            return res

        # Check subsection variants: e.g. BENAMI_2017_SEC_4_2 -> BENAMI_2017_SEC_4
        m_base = re.match(r'^(.*_(?:SEC|ART|ORD)_[0-9A-Z]+)(?:_[0-9A-Za-z]+|-.*)?$', cid_clean)
        if m_base:
            base_cid = m_base.group(1)
            res = self._by_cid.get(base_cid)
            if res:
                return res

        # Fallback to Turso statute_provisions
        try:
            from core.turso_client import get_statute_provision
            t_prov = get_statute_provision(cid_clean)
            if not t_prov and m_base:
                t_prov = get_statute_provision(m_base.group(1))
            if t_prov:
                rec = {
                    "canonical_id": t_prov.get("canonical_id"),
                    "act_code": t_prov.get("act_code"),
                    "primary_num": t_prov.get("section_num"),
                    "title": t_prov.get("title"),
                    "text": t_prov.get("verbatim_text"),
                    "tier": t_prov.get("tier", "text_layer_extracted"),
                    "in_force": bool(t_prov.get("in_force", 1)),
                    "quoting_allowed": True
                }
                self._by_cid[cid_clean] = rec
                return rec
        except Exception:
            pass

        return None

    def get_provision(self, act_code: str, provision_num: str) -> Optional[Dict[str, Any]]:
        if not self._loaded:
            self.load()
        if not act_code or not provision_num:
            return None

        act_upper = act_code.strip().upper()
        alias_map = {
            "STAMP_ACT_1899": "STAMP_1899",
            "CONTRACT_ACT_1872": "CONTRACT_1872",
            "REGISTRATION_ACT_1908": "REGISTRATION_1908",
            "LIMITATION_ACT_1908": "LIMITATION_1908",
            "BENAMI_ACT_2017": "BENAMI_2017",
            "PARTITION_ACT_1893": "PARTITION_1893",
        }
        act_upper = alias_map.get(act_upper, act_upper)
        clean_num = str(provision_num).strip().upper()
        norm_num = re.sub(r'[^A-Z0-9]', '', clean_num)

        # 1. Direct lookup by (act, num)
        rec = self._by_act_num.get((act_upper, clean_num)) or self._by_act_num.get((act_upper, norm_num))
        if rec:
            return rec

        # 2. Canonical ID variants
        # Check prefix hints in provision_num
        is_explicit_art = bool(re.search(r'\b(?:article|art)\b', str(provision_num), re.I)) or "_ART_" in clean_num
        is_explicit_sec = bool(re.search(r'\b(?:section|sec|s\.)\b', str(provision_num), re.I)) or "_SEC_" in clean_num
        
        cids_to_try = []
        if is_explicit_art or (act_upper == "LIMITATION_1908" and norm_num.isdigit() and int(norm_num) > 32):
            cids_to_try.extend([
                f"{act_upper}_ART_{clean_num}",
                f"{act_upper}_ART_{norm_num}",
                f"{act_upper}_SEC_{clean_num}",
                f"{act_upper}_SEC_{norm_num}"
            ])
        else:
            cids_to_try.extend([
                f"{act_upper}_SEC_{clean_num}",
                f"{act_upper}_SEC_{norm_num}",
                f"{act_upper}_ART_{clean_num}",
                f"{act_upper}_ART_{norm_num}"
            ])
        cids_to_try.append(f"{act_upper}_{clean_num}")
        for cid in cids_to_try:
            r = self._by_cid.get(cid)
            if r:
                return r

        # 3. Sub-section fallback e.g. 4_2 or 4(2) -> 4
        m_base_num = re.match(r'^([0-9]+[A-Za-z]*)', clean_num)
        if m_base_num and m_base_num.group(1) != clean_num:
            base_num = m_base_num.group(1)
            base_res = self.get_provision(act_upper, base_num)
            if base_res:
                return base_res

        # 4. Fallback to Turso statute_provisions
        try:
            from core.turso_client import get_statute_provision
            t_prov = get_statute_provision(f"{act_upper}_SEC_{clean_num}", act_code=act_upper)
            if not t_prov and m_base_num:
                t_prov = get_statute_provision(f"{act_upper}_SEC_{m_base_num.group(1)}", act_code=act_upper)
            if t_prov:
                rec = {
                    "canonical_id": t_prov.get("canonical_id"),
                    "act_code": t_prov.get("act_code"),
                    "primary_num": t_prov.get("section_num"),
                    "title": t_prov.get("title"),
                    "text": t_prov.get("verbatim_text"),
                    "tier": t_prov.get("tier", "text_layer_extracted"),
                    "in_force": bool(t_prov.get("in_force", 1)),
                    "quoting_allowed": True
                }
                self._by_cid[rec["canonical_id"]] = rec
                return rec
        except Exception:
            pass

        return None

# Singleton accessor
def get_unified_statute_store() -> UnifiedStatuteStore:
    return UnifiedStatuteStore()
