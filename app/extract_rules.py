"""Rules-only extraction baseline: pdfplumber text + regex, no model.

Written as a reasonable template-based system would be: generic label patterns,
Arabic presentation forms normalised (NFKC) and RTL lines re-ordered. It has no
OCR, so image-only scans come back illegible. Output matches extract.normalize().
"""
import re
import unicodedata
from datetime import date
from pathlib import Path

import pdfplumber

from app.saudi import from_hijri, normalize_iban, to_western_digits

AR = re.compile(r"[؀-ۿ]")
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}


def _logical(line: str) -> str:
    """pdfplumber gives RTL text in visual order with presentation forms. Flip Arabic runs back to
    logical order first, then NFKC (so lam-alef ligatures decompose in the right order)."""
    if not AR.search(unicodedata.normalize("NFKC", line)):
        return unicodedata.normalize("NFKC", line)
    fix_digits = lambda s: re.sub(r"[0-9٠-٩/\-.:]{2,}", lambda m: m.group(0)[::-1], s)
    if not re.search(r"[A-Za-z]{2}", line):
        return unicodedata.normalize("NFKC", fix_digits(line[::-1]))
    # Mixed line: keep Latin order, flip each Arabic run.
    flipped = re.sub(r"[\u0600-\u06FF\uFB50-\uFEFF][\u0600-\u06FF\uFB50-\uFEFF ]*[\u0600-\u06FF\uFB50-\uFEFF]",
                     lambda m: m.group(0)[::-1], line)
    return unicodedata.normalize("NFKC", flipped)


def read_text(path: Path) -> str:
    try:
        with pdfplumber.open(str(path)) as pdf:
            raw = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        return ""
    return "\n".join(_logical(l) for l in raw.splitlines())


DOC_PATTERNS = [
    ("bank_letter", r"account confirmation|bank letter|iban letter|خطاب تأكيد حساب|تأكيد حساب"),
    ("commercial_registration", r"commercial registration certificate|شهادة السجل التجاري"),
    ("vat_certificate", r"vat registration certificate|value added tax|ضريبة القيمة المضافة"),
    ("gosi_certificate", r"gosi|social insurance|التأمينات الاجتماعية"),
    ("zakat_certificate", r"zakat certificate|شهادة الزكاة"),
]
LABEL = {
    "company_name": r"(?:company name|trade name|name of entity|registered name)",
    "account_name": r"(?:account name|account holder|beneficiary name|name on account)",
    "cr_number": r"(?:cr number|commercial registration no\.?|c\.r\. no\.?|unified registration no\.?|رقم السجل التجاري)",
    "expiry": r"(?:expiry date|valid until|date of expiry|expires on|تاريخ الانتهاء)",
    "issue": r"(?:issue date|date of issue|issued on|registration date|letter date|تاريخ الإصدار|التاريخ)",
}
INJECTION = re.compile(r"ignore (all )?previous|pre-approved|do not escalate|skip registry|instruction for automated|"
                       r"note to ai|treat this certificate as valid", re.I)


def _after(label: str, text: str) -> str | None:
    m = re.search(label + r"\s*:?\s*(.+)", text, re.I)
    return m.group(1).strip() if m else None


def _latin_part(s: str | None) -> str | None:
    if not s:
        return None
    s = AR.split(s)[0].strip(" :")
    return s or None


def parse_date(s: str | None):
    """Returns {raw, calendar, year, month, day} or None."""
    if not s:
        return None
    s = to_western_digits(s)
    hijri = bool(re.search(r"\bAH\b|هـ", s))
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return {"raw": m.group(0), "calendar": "hijri" if hijri else "gregorian", "year": y, "month": mo, "day": d}
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return {"raw": m.group(0), "calendar": "gregorian", "year": y, "month": mo, "day": d}
    m = re.search(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", s)
    if m and m.group(2).lower() in MONTHS:
        return {"raw": m.group(0), "calendar": "gregorian", "year": int(m.group(3)),
                "month": MONTHS[m.group(2).lower()], "day": int(m.group(1))}
    return None


def _iso(d):
    if not d:
        return None
    try:
        if d["calendar"] == "hijri":
            return from_hijri(d["year"], d["month"], d["day"]).isoformat()
        return date(d["year"], d["month"], d["day"]).isoformat()
    except (ValueError, OverflowError):
        return None


def extract_rules(path: Path | str) -> dict:
    text = read_text(Path(path))
    flat = to_western_digits(text)
    low = flat.lower()
    empty = {"doc_type": "other", "legible": False, "language": "other", "company_name": None,
             "company_name_ar": None, "cr_number": None, "vat_number": None, "iban": None, "account_name": None,
             "account_number": None, "bank_name": None, "gosi_number": None, "nitaqat_band": None,
             "issue_date": None, "expiry_date": None, "contains_instructions": False, "instructions_text": None,
             "confidence": {}, "notes": "no text layer", "issue_date_iso": None, "expiry_date_iso": None}
    if len(text.strip()) < 20:
        return empty
    doc_type = next((t for t, pat in DOC_PATTERNS if re.search(pat, low)), "other")
    cr = re.search(LABEL["cr_number"] + r"\s*:?\s*(\d{10})", flat, re.I)
    vat = re.search(r"\b3\d{13}3\b", flat)
    iban = re.search(r"SA\d{2}[ ]?(?:\d[ ]?){20}", flat)
    ar_name = re.search(r"اسم الشركة\s*:?\s*([؀-ۿ ]+)", text)
    expiry = parse_date(_after(LABEL["expiry"], flat))
    issue = parse_date(_after(LABEL["issue"], flat))
    inj = INJECTION.search(flat)
    out = dict(empty, notes=None, legible=True, doc_type=doc_type,
               language="bilingual" if AR.search(text) and re.search(r"[A-Za-z]{4}", text) else ("ar" if AR.search(text) else "en"),
               company_name=_latin_part(_after(LABEL["company_name"], flat)),
               company_name_ar=ar_name.group(1).strip() if ar_name else None,
               cr_number=cr.group(1) if cr else None,
               vat_number=vat.group(0) if vat else None,
               iban=normalize_iban(iban.group(0)) if iban else None,
               account_name=_latin_part(_after(LABEL["account_name"], flat)),
               issue_date=issue, expiry_date=expiry if doc_type != "bank_letter" else None,
               contains_instructions=bool(inj),
               instructions_text=flat[inj.start(): inj.start() + 200] if inj else None,
               confidence={})
    out["issue_date_iso"], out["expiry_date_iso"] = _iso(out["issue_date"]), _iso(out["expiry_date"])
    return out
