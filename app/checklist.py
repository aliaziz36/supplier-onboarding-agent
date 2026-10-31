"""The full rule checklist for one case, in words a procurement manager can audit.

Display only: it re-runs checks.run_checks (deterministic, no model call) on the stored
documents at the case's as_of date, then states for each rule the values it compared and
where the reference value came from. The agent's own tool output is not changed.
"""
from app import checks
from app.saudi import BANKS, bank_code, iban_problems

DOC = {"commercial_registration": "Commercial registration", "vat_certificate": "VAT certificate",
       "bank_letter": "Bank letter", "gosi_certificate": "GOSI certificate", "zakat_certificate": "Zakat certificate"}
RULE = {
    "present": "Required document received", "legible": "Document is readable",
    "unexpired": "Document is in date", "expiry_known": "Expiry date is readable",
    "no_embedded_instructions": "No hidden instructions in documents", "confidence": "Key fields read with confidence",
    "iban_valid": "IBAN is a valid Saudi IBAN", "cr_in_registry": "CR exists in Wathq",
    "cr_active": "CR is active in Wathq", "cr_name_matches_registry": "CR name matches Wathq",
    "vat_registered": "VAT number registered with ZATCA", "bank_name_matches_cr": "Account holder is the company",
    "name_matches_cr": "Company name matches the CR", "cr_number_matches": "CR number matches across documents",
}
SOURCE = {
    "present": "policy.yaml", "legible": "document", "unexpired": "policy.yaml", "expiry_known": "document",
    "no_embedded_instructions": "document", "confidence": "policy.yaml", "iban_valid": "IBAN checksum (ISO 13616)",
    "cr_in_registry": "Wathq", "cr_active": "Wathq", "cr_name_matches_registry": "Wathq", "vat_registered": "ZATCA",
    "bank_name_matches_cr": "cross-document", "name_matches_cr": "cross-document", "cr_number_matches": "cross-document",
}


def _name(e: dict) -> str:
    return e.get("company_name") or e.get("company_name_ar") or "?"


def build(docs: list[dict], registry, policy: dict, today) -> dict:
    s = checks.run_checks(docs, registry, policy, today)
    chosen, _ = checks.pick_documents(docs)
    ex = {t: d["extraction"] for t, d in chosen.items()}
    cr = ex.get("commercial_registration", {})
    reg = registry.cr_info(cr["cr_number"]) if cr.get("cr_number") else {}
    rows = []
    for r in s["results"]:
        c, t, ok = r["check"], r.get("doc_type"), r["status"] == "pass"
        eq = "=" if ok else "≠"
        e = ex.get(t, {})
        compared = r.get("detail") or ""
        if c == "present":
            compared = f"{DOC.get(t, t)}: {'received (' + chosen[t]['filename'] + ')' if t in chosen else 'not received'}"
        elif c == "unexpired":
            compared = f"{DOC.get(t, t)} {'valid until' if ok else 'expired on'} {e.get('expiry_date_iso')}"
        elif c == "iban_valid":
            iban = e.get("iban") or ""
            code = bank_code(iban) if iban else ""
            compared = (f"IBAN {iban}: checksum passes, bank code {code} = {BANKS.get(code, (code,))[0]}"
                        if ok else f"IBAN {iban}: {', '.join(iban_problems(iban)) if iban else 'not found'}")
        elif c == "cr_in_registry":
            compared = f"CR {cr.get('cr_number')} not found in Wathq"
        elif c == "cr_active":
            compared = f"CR {cr.get('cr_number')} in Wathq: status '{reg.get('status')}'"
        elif c == "cr_name_matches_registry":
            compared = f"CR name '{_name(cr)}' {eq} Wathq name '{reg.get('name_en') or reg.get('name')}'"
        elif c == "vat_registered":
            vat = e.get("vat_number")
            compared = f"VAT {vat} in ZATCA: {'registered' if ok else 'not registered'}"
        elif c == "bank_name_matches_cr":
            compared = f"Account holder '{e.get('account_name')}' {eq} CR name '{_name(cr)}'"
        elif c == "name_matches_cr":
            compared = f"{DOC.get(t, t)} name '{_name(e)}' {eq} CR name '{_name(cr)}'"
        elif c == "cr_number_matches":
            compared = f"{DOC.get(t, t)} CR number {e.get('cr_number')} {eq} CR {cr.get('cr_number')}"
        rows.append({"check": c, "rule": RULE.get(c, c), "doc_type": t, "doc_label": DOC.get(t, t or ""),
                     "status": r["status"], "category": r["category"], "compared": compared,
                     "source": SOURCE.get(c, "")})
    return {"recommended": s["recommended"], "clean": s["clean"], "rules": rows,
            "passed": sum(r["status"] == "pass" for r in rows), "total": len(rows)}
