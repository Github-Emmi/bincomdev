"""Utilities for handling known data inconsistencies in the Bincom election dataset."""

DELTA_STATE_ID: int = 25
PARTY_ORDER: list[str] = ["PDP", "DPP", "ACN", "PPA", "CDC", "JP", "ANPP", "LABO", "CPP"]
PARTY_LABELS: dict[str, str] = {"LABO": "LABOUR"}
REQUIRED_IMPORT_TABLES: set[str] = {
    "states",
    "lga",
    "ward",
    "party",
    "polling_unit",
    "announced_pu_results",
    "announced_lga_results",
}


def normalize_party_code(code: str | None) -> str:
    """Normalize party codes to uppercase and handle known aliases.

    LABOUR (as used in the party table) is normalized to LABO (as used in results).
    """
    normalized = (code or "").strip().upper()
    if normalized == "LABOUR":
        return "LABO"
    return normalized


def party_label(code: str) -> str:
    """Get the display label for a normalized party code."""
    canonical = normalize_party_code(code)
    return PARTY_LABELS.get(canonical, canonical)


def normalize_announced_lga_key(value: str | int | None) -> str:
    """Normalize LGA identifier for use as a lookup key in announced results."""
    return str(value or "").strip()
