"""Bank-detail change guard. Exact checks only; the agent never applies a change.

Flags: iban_invalid, bank_differs_from_file, account_name_mismatch, sender_domain_mismatch.
No flags still means freeze + callback; it only lowers the risk shown to the human.
"""
from app.checks import names_match
from app.saudi import BANKS, bank_code, iban_problems, normalize_iban


def sender_domain(email: str) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().strip(">").lower()


def check_bank_change(vendor: dict, new_iban: str, account_name: str | None, sender_email: str,
                      policy: dict) -> dict:
    cfg = policy["bank_change"]
    iban = normalize_iban(new_iban)
    problems = iban_problems(iban)
    flags = []
    if problems:
        flags.append("iban_invalid")
    code = bank_code(iban) if not problems else None
    if cfg.get("flag_if_bank_differs_from_letter_on_file", True) and code and code != vendor.get("bank_code"):
        flags.append("bank_differs_from_file")
    if account_name:
        names = [vendor.get("name"), vendor.get("name_ar"), vendor.get("account_name")]
        verdicts = [names_match(account_name, n, policy) for n in names if n]
        if not any(v is True for v in verdicts):
            flags.append("account_name_mismatch")
    dom = sender_domain(sender_email)
    if cfg.get("flag_if_sender_domain_differs", True) and dom != (vendor.get("email_domain") or "").lower():
        flags.append("sender_domain_mismatch")
    return {
        "flags": flags,
        "risk": "high" if flags else "low",
        "iban": iban,
        "iban_problems": problems,
        "new_bank": BANKS.get(code, ("unknown", ""))[0] if code else None,
        "bank_on_file": BANKS.get(vendor.get("bank_code"), ("unknown", ""))[0],
        "sender_domain": dom,
        "domain_on_file": vendor.get("email_domain"),
        "callback_phone": vendor.get("phone"),
        "action": "freeze; human must call the phone number on file before any change",
    }
