"""Why the agent read a document the way it did: page image, type evidence, where each field came from.

Display only; nothing here feeds a decision. The fields and confidences are the model's
extraction as stored. This module finds them on the page: it searches the PDF's text layer
for each extracted value (and for the title words that identify the document type) and
returns the matching text with its box, so the viewer can highlight it. A scan has no text
layer, so it gets the extracted values (with the raw text the model transcribed) and no boxes.
"""
from functools import lru_cache

import arabic_reshaper
import pymupdf

from app.saudi import to_arabic_digits

# Title words and issuers that identify each document type, in English and Arabic.
TYPE_MARKERS = {
    "commercial_registration": ["Commercial Registration", "Ministry of Commerce", "السجل التجاري", "وزارة التجارة"],
    "vat_certificate": ["VAT Registration Certificate", "Zakat, Tax and Customs Authority", "ضريبة القيمة المضافة",
                        "هيئة الزكاة والضريبة والجمارك", "VAT Number", "VAT Registration Number"],
    "bank_letter": ["Account Confirmation Letter", "IBAN", "Account Holder", "خطاب تأكيد حساب", "آيبان"],
    "gosi_certificate": ["GOSI Compliance Certificate", "General Organization for Social Insurance",
                         "التأمينات الاجتماعية", "نطاقات", "Nitaqat"],
    "zakat_certificate": ["Zakat Certificate", "شهادة الزكاة"],
}
TYPE_LABEL = {"commercial_registration": "Commercial registration", "vat_certificate": "VAT certificate",
              "bank_letter": "Bank letter", "gosi_certificate": "GOSI certificate",
              "zakat_certificate": "Zakat certificate", "other": "Other document"}
FIELDS = [("company_name", "Company name"), ("company_name_ar", "Company name (Arabic)"),
          ("cr_number", "CR number"), ("vat_number", "VAT number"), ("account_name", "Account holder"),
          ("iban", "IBAN"), ("bank_name", "Bank"), ("gosi_number", "GOSI number"),
          ("nitaqat_band", "Nitaqat band"), ("issue_date", "Issue date"), ("expiry_date", "Expiry date")]
KEY_FIELDS = {"commercial_registration": ["cr_number", "company_name", "expiry_date"],
              "vat_certificate": ["vat_number", "expiry_date"], "bank_letter": ["iban", "account_name"],
              "gosi_certificate": ["expiry_date"]}
ZOOM = 2.0


def _variants(text: str) -> list[str]:
    """How a value can appear in the text layer: as is, with Arabic letters shaped, with Arabic digits,
    reversed (right-to-left runs are stored in visual order), and an IBAN in groups of four."""
    text = str(text).strip()
    out = [text, arabic_reshaper.reshape(text)]
    if any(ch.isdigit() for ch in text):
        ar = to_arabic_digits(text)
        out += [ar, ar[::-1], text[::-1]]
    if text.upper().startswith("SA") and len(text.replace(" ", "")) == 24:
        compact = text.replace(" ", "")
        out.append(" ".join(compact[i:i + 4] for i in range(0, 24, 4)))
    seen, uniq = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _lines(page) -> list[tuple[str, "pymupdf.Rect"]]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                out.append((span["text"], pymupdf.Rect(span["bbox"])))
    return out


def _find(page, text: str):
    """Exact word boxes for Latin text; for Arabic (shaped glyphs) the box of the text run that contains it."""
    variants = _variants(text)
    for v in variants:
        if v.isascii():
            hits = page.search_for(v)
            if hits:
                return v, hits[0]
    for v in variants:
        for run, rect in _lines(page):
            if v in run:
                return v, rect
    return None, None


def _box(rect, page) -> dict:
    w, h = page.rect.width, page.rect.height
    return {"x": rect.x0 / w, "y": rect.y0 / h, "w": (rect.x1 - rect.x0) / w, "h": (rect.y1 - rect.y0) / h}


def page_png(path: str) -> bytes:
    with pymupdf.open(path) as doc:
        return doc[0].get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM)).tobytes("png")


@lru_cache(maxsize=256)
def _explain(path: str, extraction_json: str) -> dict:
    import json
    ex = json.loads(extraction_json)
    t = ex.get("doc_type") or "other"
    with pymupdf.open(path) as doc:
        page = doc[0]
        has_text = bool(page.get_text().strip())
        type_evidence = []
        if has_text:
            for marker in TYPE_MARKERS.get(t, []):
                found, rect = _find(page, marker)
                if rect is not None:
                    type_evidence.append({"text": marker, "box": _box(rect, page)})
        fields = []
        conf = ex.get("confidence") or {}
        for key, label in FIELDS:
            value = ex.get(key)
            if value in (None, ""):
                continue
            iso = ex.get(f"{key}_iso")
            raw = value.get("raw") if isinstance(value, dict) else str(value)
            shown = iso or raw
            box = None
            if has_text and raw:
                _, rect = _find(page, raw)
                box = _box(rect, page) if rect is not None else None
            base = key.replace("_ar", "")
            fields.append({"field": key, "label": label, "value": shown, "source_text": raw, "box": box,
                           "confidence": conf.get(base)})
    keys = KEY_FIELDS.get(t, [])
    scores = [conf.get(k) for k in keys if isinstance(conf.get(k), (int, float))]
    return {"doc_type": t, "label": TYPE_LABEL.get(t, t), "language": ex.get("language"),
            "legible": ex.get("legible"), "has_text_layer": has_text, "type_evidence": type_evidence,
            "fields": fields, "confidence": min(scores) if scores else None, "confidence_fields": keys}


def explain(path: str, extraction_json: str) -> dict:
    return _explain(path, extraction_json)
