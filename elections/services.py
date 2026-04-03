from collections import defaultdict
from functools import lru_cache

from django.db.models import Count, IntegerField, Max, Sum
from django.db.models.functions import Cast

from .models import AnnouncedPUResult, LGA, Party, PollingUnit, SequenceCounter, Ward
from .source_quirks import DELTA_STATE_ID, PARTY_ORDER, normalize_party_code, party_label


def ordered_parties() -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}

    for party in Party.objects.order_by("id"):
        canonical = normalize_party_code(party.partyid)
        seen[canonical] = {"code": canonical, "label": party_label(canonical)}

    for code in PARTY_ORDER:
        seen.setdefault(code, {"code": code, "label": party_label(code)})

    return [seen[code] for code in PARTY_ORDER if code in seen]


def delta_lgas_queryset():
    return LGA.objects.filter(state_id=DELTA_STATE_ID).order_by("lga_name")


def displayable_polling_units_queryset(with_results_only: bool = False):
    # The source dump contains 170 placeholder polling-unit rows with blank labels or zero IDs.
    # This queryset defines the shared "usable polling unit" rule used across the UI.
    queryset = (
        PollingUnit.objects.filter(
            lga_id__in=delta_lgas_queryset().values_list("lga_id", flat=True)
        )
        .exclude(polling_unit_number__isnull=True)
        .exclude(polling_unit_number="")
        .exclude(polling_unit_name__isnull=True)
        .exclude(polling_unit_name="")
        .exclude(lga_id=0)
        .exclude(polling_unit_id=0)
    )

    if with_results_only:
        polling_unit_ids = (
            AnnouncedPUResult.objects.annotate(
                polling_unit_uniqueid_int=Cast("polling_unit_uniqueid", IntegerField())
            )
            .values("polling_unit_uniqueid_int")
            .distinct()
        )
        queryset = queryset.filter(uniqueid__in=polling_unit_ids)

    return queryset.order_by("polling_unit_name", "polling_unit_number")


def aggregate_party_scores(results_queryset):
    totals = defaultdict(int)
    row_counts = defaultdict(int)
    aggregated_rows = results_queryset.values("party_abbreviation").annotate(
        score=Sum("party_score"),
        row_count=Count("party_abbreviation"),
    )

    for row in aggregated_rows:
        code = normalize_party_code(row["party_abbreviation"])
        totals[code] += row["score"] or 0
        row_counts[code] += row["row_count"] or 0

    grand_total = sum(totals.values())
    top_score = max(totals.values(), default=0)
    rows = []

    for party in ordered_parties():
        score = totals.get(party["code"], 0)
        rows.append(
            {
                "code": party["code"],
                "label": party["label"],
                "score": score,
                "share": round((score / grand_total) * 100, 1) if grand_total else 0,
                "bar_width": round((score / top_score) * 100, 1) if top_score else 0,
                "row_count": row_counts.get(party["code"], 0),
            }
        )

    return {
        "rows": rows,
        "grand_total": grand_total,
        "raw_entry_count": sum(row_counts.values()),
    }


def allocate_next_polling_unit_id() -> int:
    counter, _ = SequenceCounter.objects.select_for_update().get_or_create(
        name="polling_unit_id",
        defaults={
            "next_value": (
                PollingUnit.objects.aggregate(max_id=Max("polling_unit_id"))["max_id"] or 0
            )
            + 1
        },
    )
    current_value = counter.next_value
    counter.next_value = current_value + 1
    counter.save(update_fields=["next_value"])
    return current_value


@lru_cache(maxsize=1)
def ward_lookup() -> dict[int, Ward]:
    return {ward.uniqueid: ward for ward in Ward.objects.all()}


@lru_cache(maxsize=1)
def lga_lookup() -> dict[int, LGA]:
    return {lga.lga_id: lga for lga in delta_lgas_queryset()}


def clear_lookup_caches() -> None:
    ward_lookup.cache_clear()
    lga_lookup.cache_clear()
