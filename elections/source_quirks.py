DELTA_STATE_ID = 25
PARTY_ORDER = ["PDP", "DPP", "ACN", "PPA", "CDC", "JP", "ANPP", "LABO", "CPP"]
PARTY_LABELS = {"LABO": "LABOUR"}
REQUIRED_IMPORT_TABLES = {
    "states",
    "lga",
    "ward",
    "party",
    "polling_unit",
    "announced_pu_results",
    "announced_lga_results",
}


def normalize_party_code(code: str | None) -> str:
    normalized = (code or "").strip().upper()
    if normalized == "LABOUR":
        return "LABO"
    return normalized


def party_label(code: str) -> str:
    canonical = normalize_party_code(code)
    return PARTY_LABELS.get(canonical, canonical)


def normalize_announced_lga_key(value: str | int | None) -> str:
    return str(value or "").strip()
