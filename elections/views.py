from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import PollingUnitSubmissionForm
from .models import AnnouncedLGAResult, AnnouncedPUResult, Ward
from .services import (
    aggregate_party_scores,
    clear_lookup_caches,
    delta_lgas_queryset,
    displayable_polling_units_queryset,
    lga_lookup,
    ward_lookup,
)
from .source_quirks import normalize_announced_lga_key


def dashboard(request):
    result_units = displayable_polling_units_queryset(with_results_only=True)
    lgas_with_results = (
        delta_lgas_queryset()
        .filter(lga_id__in=result_units.values_list("lga_id", flat=True).distinct())
        .order_by("lga_name")
    )

    context = {
        "summary": {
            "lga_count": delta_lgas_queryset().count(),
            "ward_count": Ward.objects.filter(
                lga_id__in=delta_lgas_queryset().values_list("lga_id", flat=True)
            ).count(),
            "polling_unit_count": displayable_polling_units_queryset().count(),
            "result_polling_unit_count": result_units.count(),
            "announced_pu_rows": AnnouncedPUResult.objects.count(),
        },
        "lgas_with_results": lgas_with_results[:8],
        "architecture_steps": [
            "Import the Delta State election dataset from the provided SQL dump into Django models.",
            "Filter out placeholder polling units so selectors focus on meaningful records.",
            "Show individual polling unit results with LGA and ward chained selectors.",
            "Compute LGA totals by summing polling unit results instead of reading announced LGA totals.",
            "Capture new polling unit submissions and persist one score per party.",
            "Prepare the app for Render deployment with static file support and a repeatable import command.",
        ],
    }
    return render(request, "elections/dashboard.html", context)


def polling_unit_results(request):
    result_units = displayable_polling_units_queryset(with_results_only=True)
    ward_map = ward_lookup()
    lga_map = lga_lookup()
    available_lgas = (
        delta_lgas_queryset()
        .filter(lga_id__in=result_units.values_list("lga_id", flat=True).distinct())
        .order_by("lga_name")
    )

    selected_lga_id = request.GET.get("lga") or (
        str(available_lgas.first().lga_id) if available_lgas else None
    )
    ward_options = Ward.objects.none()
    polling_unit_options = result_units.none()

    if selected_lga_id:
        polling_unit_options = result_units.filter(lga_id=selected_lga_id)
        ward_ids = polling_unit_options.values_list("uniquewardid", flat=True).distinct()
        ward_options = Ward.objects.filter(uniqueid__in=ward_ids).order_by("ward_name")

    selected_ward_id = request.GET.get("ward") or (
        str(ward_options.first().uniqueid) if ward_options else None
    )
    if selected_ward_id:
        polling_unit_options = polling_unit_options.filter(uniquewardid=selected_ward_id)

    selected_polling_unit_id = request.GET.get("polling_unit") or (
        str(polling_unit_options.first().uniqueid) if polling_unit_options else None
    )
    polling_unit = (
        polling_unit_options.filter(uniqueid=selected_polling_unit_id).first()
        if selected_polling_unit_id
        else None
    )

    aggregated_results = (
        aggregate_party_scores(
            AnnouncedPUResult.objects.filter(
                polling_unit_uniqueid=str(polling_unit.uniqueid)
            )
        )
        if polling_unit
        else {"rows": [], "grand_total": 0, "raw_entry_count": 0}
    )

    context = {
        "available_lgas": available_lgas,
        "ward_options": ward_options,
        "polling_unit_options": polling_unit_options,
        "polling_unit": polling_unit,
        "aggregated_results": aggregated_results,
        "selected_lga_id": str(selected_lga_id) if selected_lga_id else "",
        "selected_ward_id": str(selected_ward_id) if selected_ward_id else "",
        "selected_polling_unit_id": str(selected_polling_unit_id) if selected_polling_unit_id else "",
        "selected_lga": lga_map.get(int(selected_lga_id)) if selected_lga_id else None,
        "selected_ward": ward_map.get(int(selected_ward_id)) if selected_ward_id else None,
    }
    return render(request, "elections/polling_unit_detail.html", context)


def lga_results(request):
    result_units = displayable_polling_units_queryset(with_results_only=True)
    available_lgas = (
        delta_lgas_queryset()
        .filter(lga_id__in=result_units.values_list("lga_id", flat=True).distinct())
        .order_by("lga_name")
    )
    selected_lga_id = request.GET.get("lga") or (
        str(available_lgas.first().lga_id) if available_lgas else None
    )

    polling_units = result_units.none()
    calculated = {"rows": [], "grand_total": 0, "raw_entry_count": 0}
    comparison_rows = []
    announced_total = 0
    selected_lga = None

    if selected_lga_id:
        selected_lga = available_lgas.filter(lga_id=selected_lga_id).first()
        polling_units = result_units.filter(lga_id=selected_lga_id)
        results = AnnouncedPUResult.objects.filter(
            polling_unit_uniqueid__in=[
                str(pk) for pk in polling_units.values_list("uniqueid", flat=True)
            ]
        )
        calculated = aggregate_party_scores(results)
        announced = aggregate_party_scores(
            AnnouncedLGAResult.objects.filter(
                lga_name=normalize_announced_lga_key(selected_lga_id)
            )
        )
        announced_by_code = {row["code"]: row["score"] for row in announced["rows"]}
        announced_total = announced["grand_total"]

        for row in calculated["rows"]:
            announced_score = announced_by_code.get(row["code"], 0)
            comparison_rows.append(
                {
                    **row,
                    "announced_score": announced_score,
                    "difference": row["score"] - announced_score,
                }
            )

    context = {
        "available_lgas": available_lgas,
        "selected_lga_id": str(selected_lga_id) if selected_lga_id else "",
        "selected_lga": selected_lga,
        "polling_unit_count": polling_units.count(),
        "calculated": calculated,
        "announced_total": announced_total,
        "comparison_rows": comparison_rows,
    }
    return render(request, "elections/lga_results.html", context)


def create_polling_unit(request):
    if request.method == "POST":
        form = PollingUnitSubmissionForm(request.POST)
        if form.is_valid():
            polling_unit = form.save(request)
            clear_lookup_caches()
            messages.success(
                request,
                "The polling unit and all party scores were saved successfully.",
            )
            return redirect(
                f"{reverse('elections:polling-unit-results')}?lga={polling_unit.lga_id}&ward={polling_unit.uniquewardid}&polling_unit={polling_unit.uniqueid}"
            )
    else:
        form = PollingUnitSubmissionForm()

    return render(request, "elections/polling_unit_form.html", {"form": form})


def wards_api(request):
    lga_id = request.GET.get("lga_id")
    with_results = request.GET.get("with_results") == "1"
    queryset = Ward.objects.all()

    if lga_id:
        queryset = queryset.filter(lga_id=lga_id)

    if with_results and lga_id:
        result_units = displayable_polling_units_queryset(with_results_only=True).filter(
            lga_id=lga_id
        )
        ward_ids = result_units.values_list("uniquewardid", flat=True).distinct()
        queryset = queryset.filter(uniqueid__in=ward_ids)

    items = [{"id": ward.uniqueid, "name": ward.ward_name} for ward in queryset.order_by("ward_name")]
    return JsonResponse({"items": items})


def polling_units_api(request):
    lga_id = request.GET.get("lga_id")
    ward_id = request.GET.get("ward_id")
    with_results = request.GET.get("with_results") == "1"

    queryset = displayable_polling_units_queryset(with_results_only=with_results)
    if lga_id:
        queryset = queryset.filter(lga_id=lga_id)
    if ward_id:
        queryset = queryset.filter(uniquewardid=ward_id)

    items = [
        {
            "id": polling_unit.uniqueid,
            "name": polling_unit.polling_unit_name,
            "number": polling_unit.polling_unit_number,
        }
        for polling_unit in queryset
    ]
    return JsonResponse({"items": items})
