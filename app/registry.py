"""Mock Saudi registries, shaped like the real services so they are swap-ready.

- Wathq CR info (/info/{id}): name (Arabic), name_en, status, issue/expiry dates.
- ZATCA VAT verification: registered yes/no plus the name on the registration.

Records come from each case folder's world.json (the generator writes them),
so every case carries its own slice of the outside world.
"""
import json
from pathlib import Path


class Registry:
    def __init__(self, cr: dict | None = None, vat: dict | None = None):
        self.cr = dict(cr or {})
        self.vat = dict(vat or {})

    def add_world(self, world: dict) -> None:
        reg = world.get("registry", {})
        self.cr.update(reg.get("cr", {}))
        self.vat.update(reg.get("vat", {}))

    def cr_info(self, cr_number: str) -> dict:
        rec = self.cr.get(str(cr_number).strip())
        if not rec:
            return {"found": False, "crNumber": cr_number}
        return {"found": True, "crNumber": cr_number, **rec}

    def vat_check(self, vat_number: str) -> dict:
        rec = self.vat.get(str(vat_number).strip())
        if not rec:
            return {"registered": False, "vatNumber": vat_number}
        return {"vatNumber": vat_number, **rec}


def load_world(case_dir: Path) -> dict:
    path = Path(case_dir) / "world.json"
    return json.loads(path.read_text()) if path.exists() else {}


def registry_for_cases(case_dirs) -> Registry:
    reg = Registry()
    for d in case_dirs:
        reg.add_world(load_world(d))
    return reg
