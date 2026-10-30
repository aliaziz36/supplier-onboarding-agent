"""Saudi reference data and exact helpers: banks, IBAN checksum, Hijri dates, digits."""
from datetime import date

# 2-digit bank code inside a Saudi IBAN (SAkk BB AAAAAAAAAAAAAAAAAA).
BANKS = {
    "10": ("Saudi National Bank", "البنك الأهلي السعودي"),
    "20": ("Riyad Bank", "بنك الرياض"),
    "30": ("Arab National Bank", "البنك العربي الوطني"),
    "45": ("Saudi Awwal Bank", "البنك السعودي الأول"),
    "55": ("Banque Saudi Fransi", "البنك السعودي الفرنسي"),
    "60": ("Bank AlJazira", "بنك الجزيرة"),
    "80": ("Al Rajhi Bank", "مصرف الراجحي"),
    "05": ("Alinma Bank", "مصرف الإنماء"),
    "15": ("Bank AlBilad", "بنك البلاد"),
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def to_western_digits(s: str) -> str:
    return (s or "").translate(ARABIC_DIGITS)


def to_arabic_digits(s: str) -> str:
    return s.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def _mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97


def make_iban(bank_code: str, account: str) -> str:
    """Build a valid Saudi IBAN from a 2-digit bank code and 18-digit account."""
    assert len(bank_code) == 2 and len(account) == 18
    body = f"SA00{bank_code}{account}"
    check = 98 - _mod97(body)
    return f"SA{check:02d}{bank_code}{account}"


def normalize_iban(iban: str) -> str:
    return to_western_digits(iban or "").replace(" ", "").replace("-", "").upper()


def iban_problems(iban: str) -> list[str]:
    """Empty list = valid Saudi IBAN."""
    s = normalize_iban(iban)
    if not s.startswith("SA"):
        return ["not_saudi_iban"]
    if len(s) != 24 or not s[2:].isdigit():
        return ["bad_length_or_chars"]
    if _mod97(s) != 1:
        return ["bad_checksum"]
    if s[4:6] not in BANKS:
        return ["unknown_bank_code"]
    return []


def bank_code(iban: str) -> str:
    return normalize_iban(iban)[4:6]


def to_hijri(d: date) -> tuple[int, int, int]:
    from hijridate import Gregorian
    h = Gregorian(d.year, d.month, d.day).to_hijri()
    return h.year, h.month, h.day


def from_hijri(y: int, m: int, d: int) -> date:
    from hijridate import Hijri
    return Hijri(y, m, d).to_gregorian()
