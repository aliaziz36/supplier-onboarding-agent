"""Deterministic onboarding checks, driven by policy.yaml. No model calls here.

Each result: {check, status: pass|fail, category: fixable|risk, doc_type, detail}.
fixable -> the supplier can fix it by email; risk -> a human decides.
"""
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

from app.registry import Registry

EXPIRING = {"commercial_registration", "vat_certificate", "gosi_certificate", "zakat_certificate"}
ARABIC_LEGAL = {"شركة", "مؤسسة", "مؤسسه", "شركه", "ذ.م.م", "المحدودة"}
_AR_DIACRITICS = re.compile(r"[ً-ٰٟـ]")


def is_arabic(s: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in s or "")


def normalize_name(name: str, policy: dict) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).lower()
    if is_arabic(s):
        s = _AR_DIACRITICS.sub("", s)
        s = re.sub("[إأآا]", "ا", s).replace("ة", "ه").replace("ى", "ي")
        tokens = [t for t in re.split(r"\s+", s) if t and t not in ARABIC_LEGAL]
        return " ".join(tokens)
    s = s.replace("-", " ").replace("&", " and ")
    ignore = {x.lower().rstrip(".") for x in policy["checks"]["name_match"]["ignore_suffixes"]}
    ignore |= {"l.l.c", "llc", "limited", "establishment", "company", "co", "est", "ltd"}
    tokens = [t.strip(".,") for t in s.split()]
    tokens = [t for t in tokens if t and t.replace(".", "") not in {i.replace(".", "") for i in ignore}]
    return " ".join(tokens)


def names_match(a: str, b: str, policy: dict) -> bool | None:
    """True/False when comparable (same script); None when scripts differ."""
    if not a or not b or is_arabic(a) != is_arabic(b):
        return None
    na, nb = normalize_name(a, policy), normalize_name(b, policy)
    if not na or not nb:
        return None
    if na.replace(" ", "") == nb.replace(" ", ""):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= policy["checks"]["name_match"]["min_similarity"]


def any_match(names_a: list, names_b: list, policy: dict) -> bool | None:
    verdicts = [names_match(a, b, policy) for a in names_a for b in names_b]
    if any(v is True for v in verdicts):
        return True
    if any(v is False for v in verdicts):
        return False
    return None


def pick_documents(docs: list[dict]) -> tuple[dict, list[dict]]:
    """Latest legible extraction per doc type, plus the illegible ones.

    docs: [{id, filename, received_at, extraction}] in arrival order.
    """
    chosen, illegible = {}, []
    for d in docs:
        ex = d.get("extraction")
        if not ex:
            continue
        if not ex.get("legible", True):
            illegible.append(d)
            continue
        t = ex.get("doc_type")
        if t and t != "other":
            chosen[t] = d          # later arrivals replace earlier ones
    return chosen, illegible


def run_checks(docs: list[dict], registry: Registry | None, policy: dict, today: date,
               ablate: set | None = None) -> dict:
    ablate = set(ablate or ())
    results = []

    def add(check, ok, category, doc_type=None, detail=""):
        results.append({"check": check, "status": "pass" if ok else "fail", "category": category,
                        "doc_type": doc_type, "detail": detail})

    chosen, illegible = pick_documents(docs)
    required = list(policy["required_documents"])
    ex = {t: d["extraction"] for t, d in chosen.items()}

    # Illegible documents: ask for a clearer copy of whatever type we could not read.
    for d in illegible:
        t = d["extraction"].get("doc_type")
        if t in required and t not in chosen:
            add("legible", False, "fixable", t, f"{d['filename']} could not be read; need a clearer copy")

    # Required documents present.
    for t in required:
        if t not in chosen and not any(r["doc_type"] == t and r["check"] == "legible" for r in results):
            add("present", False, "fixable", t, f"{t} not received")
        elif t in chosen:
            add("present", True, "fixable", t)

    # Expiry.
    if policy["checks"].get("document_must_be_unexpired", True):
        for t, e in ex.items():
            if t not in EXPIRING or t not in required:
                continue
            exp = e.get("expiry_date_iso")
            if not exp:
                add("expiry_known", False, "risk", t, "no readable expiry date")
            elif date.fromisoformat(exp) < today:
                add("unexpired", False, "fixable", t, f"expired on {exp}")
            else:
                add("unexpired", True, "fixable", t, f"valid until {exp}")

    # Prompt injection is a fraud signal on its own.
    for d in docs:
        e = d.get("extraction") or {}
        if e.get("contains_instructions"):
            add("no_embedded_instructions", False, "risk", e.get("doc_type"),
                f"{d['filename']}: {(e.get('instructions_text') or '')[:200]}")

    # Low confidence on key fields that the document type should carry.
    min_conf = policy["extraction"]["min_confidence_for_key_fields"]
    relevant = {
        "commercial_registration": ["cr_number", "company_name", "expiry_date"],
        "vat_certificate": ["vat_number", "expiry_date"],
        "bank_letter": ["iban", "account_name"],
        "gosi_certificate": ["expiry_date"],
    }
    for t, e in ex.items():
        for f in relevant.get(t, []):
            conf = (e.get("confidence") or {}).get(f, 1.0)
            if conf < min_conf:
                add("confidence", False, "risk", t, f"low confidence ({conf:.2f}) on {f}")

    cr_doc = ex.get("commercial_registration", {})
    cr_number = cr_doc.get("cr_number")
    reg_names = []

    # Registry: Wathq CR status, ZATCA VAT registration.
    if "registry" not in ablate and registry is not None:
        if cr_number and policy["checks"].get("cr_must_be_active_in_registry", True):
            info = registry.cr_info(cr_number)
            if not info.get("found"):
                add("cr_in_registry", False, "risk", "commercial_registration", f"CR {cr_number} not found")
            else:
                reg_names = [info.get("name"), info.get("name_en")]
                add("cr_active", info.get("status") == "active", "risk", "commercial_registration",
                    f"registry status: {info.get('status')}")
                if cr_doc.get("company_name") or cr_doc.get("company_name_ar"):
                    m = any_match([cr_doc.get("company_name"), cr_doc.get("company_name_ar")], reg_names, policy)
                    if m is not None:
                        add("cr_name_matches_registry", m, "risk", "commercial_registration",
                            f"document '{cr_doc.get('company_name') or cr_doc.get('company_name_ar')}' vs registry '{info.get('name_en')}'")
        vat_number = ex.get("vat_certificate", {}).get("vat_number")
        if vat_number and policy["checks"].get("vat_must_be_registered", True):
            v = registry.vat_check(vat_number)
            add("vat_registered", bool(v.get("registered")), "risk", "vat_certificate",
                f"ZATCA: {'registered' if v.get('registered') else 'not registered'}")

    # Cross-document consistency.
    if "crossdoc" not in ablate:
        company_names = [cr_doc.get("company_name"), cr_doc.get("company_name_ar")] + reg_names
        company_names = [n for n in company_names if n]
        if "bank_letter" in ex and policy["checks"].get("bank_account_name_must_match_cr_name", True):
            acct = ex["bank_letter"].get("account_name")
            m = any_match([acct], company_names, policy) if acct else None
            if m is not None:  # None = different scripts with no bridge; cannot compare
                add("bank_name_matches_cr", m, "risk", "bank_letter", f"account holder '{acct}'")
        for t in ("vat_certificate", "gosi_certificate"):
            if t in ex and company_names:
                names = [ex[t].get("company_name"), ex[t].get("company_name_ar")]
                m = any_match(names, company_names, policy)
                if m is not None:
                    add("name_matches_cr", m, "risk", t, f"'{ex[t].get('company_name') or ex[t].get('company_name_ar')}'")
        if cr_number and policy["checks"].get("cr_number_must_match_across_documents", True):
            for t, e in ex.items():
                if t != "commercial_registration" and e.get("cr_number"):
                    add("cr_number_matches", e["cr_number"] == cr_number, "risk", t,
                        f"{e['cr_number']} vs CR {cr_number}")

    return summarize(results)


def summarize(results: list[dict]) -> dict:
    fails = [r for r in results if r["status"] == "fail"]
    risk = [r for r in fails if r["category"] == "risk"]
    fixable = [r for r in fails if r["category"] == "fixable"]
    to_request = sorted({r["doc_type"] for r in fixable if r["doc_type"]})
    if risk:
        recommended = "escalate"
    elif fixable:
        recommended = "request_fix"
    else:
        recommended = "onboard"
    return {"clean": not fails, "recommended": recommended, "risk": risk, "fixable": fixable,
            "documents_to_request": to_request, "results": results}
