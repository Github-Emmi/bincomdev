import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count, Max, Min, Q

from elections.models import AnnouncedPUResult, Party, PollingUnit


PLACEHOLDER_FILTER = (
    Q(polling_unit_number__isnull=True)
    | Q(polling_unit_number="")
    | Q(polling_unit_name__isnull=True)
    | Q(polling_unit_name="")
    | Q(lga_id=0)
    | Q(polling_unit_id=0)
)


class Command(BaseCommand):
    help = "Audit the Bincom election dataset for known inconsistencies and emit a data-quality report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default="analysis_outputs/data_quality_report.json",
            help="Optional JSON output path for the generated report.",
        )

    def handle(self, *args, **options):
        report = self._build_report()
        output_path = options.get("out")

        self.stdout.write("Bincom data-quality summary")
        self.stdout.write(f"- Placeholder polling units: {report['placeholder_polling_units']}")
        self.stdout.write(
            f"- Duplicate polling_unit_id groups: {report['duplicate_polling_unit_id_groups']}"
        )
        self.stdout.write(f"- Ward/LGA mismatch rows: {report['polling_unit_lga_ward_mismatches']}")
        self.stdout.write(
            f"- Result-backed polling units: {report['distinct_result_polling_units']}"
        )
        self.stdout.write(
            f"- Result-backed LGAs: {report['result_backed_lgas']} of {report['delta_lga_count']}"
        )

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))

    def _build_report(self):
        placeholder_polling_units = PollingUnit.objects.filter(PLACEHOLDER_FILTER).count()
        duplicate_groups = list(
            PollingUnit.objects.values("polling_unit_id")
            .annotate(
                row_count=Count("uniqueid"),
                min_uniqueid=Min("uniqueid"),
                max_uniqueid=Max("uniqueid"),
            )
            .filter(row_count__gt=1)
            .order_by("polling_unit_id")
        )

        party_codes = sorted({party.partyid.upper() for party in Party.objects.all()})
        result_party_codes = sorted(
            {code.upper() for code in AnnouncedPUResult.objects.values_list("party_abbreviation", flat=True)}
        )

        with connection.cursor() as cursor:
            distinct_result_rows = AnnouncedPUResult.objects.values("polling_unit_uniqueid").distinct().count()

            cursor.execute(
                """
                SELECT COUNT(DISTINCT pu.lga_id)
                FROM announced_pu_results r
                JOIN polling_unit pu ON pu.uniqueid = CAST(r.polling_unit_uniqueid AS INTEGER)
                """
            )
            result_backed_lgas = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT pu.uniqueid, pu.polling_unit_id, pu.lga_id, pu.uniquewardid,
                       w.lga_id AS ward_lga_id, w.ward_name, pu.polling_unit_number, pu.polling_unit_name
                FROM polling_unit pu
                JOIN ward w ON w.uniqueid = pu.uniquewardid
                WHERE pu.lga_id != w.lga_id
                """
            )
            mismatch_rows = [
                {
                    "uniqueid": row[0],
                    "polling_unit_id": row[1],
                    "polling_unit_lga_id": row[2],
                    "uniquewardid": row[3],
                    "ward_lga_id": row[4],
                    "ward_name": row[5],
                    "polling_unit_number": row[6],
                    "polling_unit_name": row[7],
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                WITH pu_scores AS (
                    SELECT pu.lga_id, r.party_abbreviation, SUM(r.party_score) AS pu_score
                    FROM announced_pu_results r
                    JOIN polling_unit pu ON pu.uniqueid = CAST(r.polling_unit_uniqueid AS INTEGER)
                    GROUP BY pu.lga_id, r.party_abbreviation
                ),
                lga_scores AS (
                    SELECT CAST(lga_name AS INTEGER) AS lga_id, party_abbreviation, SUM(party_score) AS lga_score
                    FROM announced_lga_results
                    GROUP BY CAST(lga_name AS INTEGER), party_abbreviation
                )
                SELECT l.lga_name, pu_scores.party_abbreviation, pu_scores.pu_score,
                       COALESCE(lga_scores.lga_score, 0) AS lga_score,
                       pu_scores.pu_score - COALESCE(lga_scores.lga_score, 0) AS diff
                FROM pu_scores
                JOIN lga l ON l.lga_id = pu_scores.lga_id AND l.state_id = 25
                LEFT JOIN lga_scores
                    ON lga_scores.lga_id = pu_scores.lga_id
                   AND lga_scores.party_abbreviation = pu_scores.party_abbreviation
                ORDER BY ABS(diff) DESC
                LIMIT 10
                """
            )
            lga_gap_rows = [
                {
                    "lga_name": row[0],
                    "party_abbreviation": row[1],
                    "polling_unit_sum": row[2],
                    "announced_lga_sum": row[3],
                    "difference": row[4],
                }
                for row in cursor.fetchall()
            ]

        return {
            "delta_lga_count": 25,
            "placeholder_polling_units": placeholder_polling_units,
            "duplicate_polling_unit_id_groups": len(duplicate_groups),
            "duplicate_polling_unit_id_examples": duplicate_groups[:10],
            "distinct_result_polling_units": distinct_result_rows,
            "result_backed_lgas": result_backed_lgas,
            "polling_unit_lga_ward_mismatches": len(mismatch_rows),
            "polling_unit_lga_ward_mismatch_examples": mismatch_rows,
            "party_table_codes": party_codes,
            "result_table_codes": result_party_codes,
            "party_code_note": "LABOUR is used in the party table while LABO is used in result tables.",
            "announced_lga_key_note": "announced_lga_results.lga_name stores numeric LGA IDs as strings.",
            "largest_lga_comparison_gaps": lga_gap_rows,
            "recommendations": [
                "Continue filtering placeholder polling units out of selectors and analytics.",
                "Use polling_unit.uniqueid as the true application identity; polling_unit_id is reused in source data.",
                "Surface ward/LGA mismatches in audit tooling before trusting relational joins.",
                "Normalize LABOUR and LABO through one shared canonicalization function.",
                "Treat announced LGA totals as a cross-check view because polling-unit coverage is incomplete.",
            ],
        }
