import csv
import io
import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from elections.models import (
    LGA,
    AnnouncedLGAResult,
    AnnouncedPUResult,
    Party,
    PollingUnit,
    SequenceCounter,
    State,
    Ward,
)
from elections.services import clear_lookup_caches
from elections.source_quirks import REQUIRED_IMPORT_TABLES


INSERT_PATTERN = re.compile(
    r"INSERT INTO `(?P<table>[^`]+)` \((?P<columns>.*?)\) VALUES\s*(?P<values>.*?);(?=\s*(?:--|\Z))",
    re.S,
)


class Command(BaseCommand):
    help = "Import the provided `bincom_test.sql` dump into the local Django database."

    def add_arguments(self, parser):
        parser.add_argument("--path", default="bincom_test.sql", help="Path to the SQL dump file.")

    def handle(self, *args, **options):
        sql_path = Path(options["path"])
        if not sql_path.exists():
            raise CommandError(f"SQL file not found: {sql_path}")

        sql_text = sql_path.read_text(encoding="utf-8")
        inserts = self._extract_inserts(sql_text)
        self._validate_required_tables(inserts)

        with transaction.atomic():
            AnnouncedPUResult.objects.all().delete()
            AnnouncedLGAResult.objects.all().delete()
            PollingUnit.objects.all().delete()
            Ward.objects.all().delete()
            LGA.objects.all().delete()
            Party.objects.all().delete()
            State.objects.all().delete()
            SequenceCounter.objects.all().delete()

            self._import_states(inserts.get("states", []))
            self._import_lgas(inserts.get("lga", []))
            self._import_wards(inserts.get("ward", []))
            self._import_parties(inserts.get("party", []))
            self._import_polling_units(inserts.get("polling_unit", []))
            self._import_announced_pu_results(inserts.get("announced_pu_results", []))
            self._import_announced_lga_results(inserts.get("announced_lga_results", []))
            SequenceCounter.objects.update_or_create(
                name="polling_unit_id",
                defaults={
                    "next_value": (
                        PollingUnit.objects.aggregate(max_id=Max("polling_unit_id"))["max_id"] or 0
                    )
                    + 1
                },
            )

        clear_lookup_caches()

        self.stdout.write(self.style.SUCCESS("Bincom SQL data imported successfully."))

    def _extract_inserts(self, sql_text: str) -> dict[str, list[dict[str, str | None]]]:
        inserts: dict[str, list[dict[str, str | None]]] = {}

        for match in INSERT_PATTERN.finditer(sql_text):
            table = match.group("table")
            columns = [column.strip(" `") for column in match.group("columns").split(",")]
            values_block = match.group("values").strip()
            rows = []
            for row_string in self._split_rows(values_block):
                reader = csv.reader(
                    io.StringIO(row_string),
                    delimiter=",",
                    quotechar="'",
                    escapechar="\\",
                    skipinitialspace=True,
                )
                values = next(reader)
                rows.append(
                    {
                        column: self._clean_sql_value(value)
                        for column, value in zip(columns, values, strict=False)
                    }
                )
            inserts[table] = rows

        return inserts

    def _validate_required_tables(self, inserts):
        missing = sorted(REQUIRED_IMPORT_TABLES - set(inserts))
        if missing:
            raise CommandError(
                f"SQL import failed. Missing required tables: {', '.join(missing)}"
            )

        empty = sorted(table for table in REQUIRED_IMPORT_TABLES if not inserts.get(table))
        if empty:
            raise CommandError(
                f"SQL import failed. Required tables were found but empty: {', '.join(empty)}"
            )

    def _split_rows(self, values_block: str) -> list[str]:
        rows = []
        current = []
        depth = 0
        in_quote = False
        escape_next = False

        for char in values_block:
            if escape_next:
                current.append(char)
                escape_next = False
                continue

            if char == "\\" and in_quote:
                current.append(char)
                escape_next = True
                continue

            if char == "'" and depth > 0:
                in_quote = not in_quote
                current.append(char)
                continue

            if not in_quote and char == "(":
                if depth > 0:
                    current.append(char)
                depth += 1
                continue

            if not in_quote and char == ")":
                depth -= 1
                if depth == 0:
                    rows.append("".join(current))
                    current = []
                    continue
                current.append(char)
                continue

            if depth > 0:
                current.append(char)

        return rows

    def _clean_sql_value(self, value: str) -> str | None:
        cleaned = value.strip()
        if cleaned == "NULL":
            return None
        return cleaned

    def _parse_datetime(self, value: str | None):
        if not value or value == "0000-00-00 00:00:00":
            return None
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return timezone.make_aware(parsed, timezone.get_current_timezone())

    def _import_states(self, rows):
        State.objects.bulk_create(
            [State(state_id=int(row["state_id"]), state_name=row["state_name"] or "") for row in rows]
        )

    def _import_lgas(self, rows):
        LGA.objects.bulk_create(
            [
                LGA(
                    uniqueid=int(row["uniqueid"]),
                    lga_id=int(row["lga_id"]),
                    lga_name=row["lga_name"] or "",
                    state_id=int(row["state_id"]),
                    lga_description=row["lga_description"],
                    entered_by_user=row["entered_by_user"] or "",
                    date_entered=self._parse_datetime(row["date_entered"]),
                    user_ip_address=row["user_ip_address"] or "",
                )
                for row in rows
            ]
        )

    def _import_wards(self, rows):
        Ward.objects.bulk_create(
            [
                Ward(
                    uniqueid=int(row["uniqueid"]),
                    ward_id=int(row["ward_id"]),
                    ward_name=row["ward_name"] or "",
                    lga_id=int(row["lga_id"]),
                    ward_description=row["ward_description"],
                    entered_by_user=row["entered_by_user"] or "",
                    date_entered=self._parse_datetime(row["date_entered"]),
                    user_ip_address=row["user_ip_address"] or "",
                )
                for row in rows
            ]
        )

    def _import_parties(self, rows):
        Party.objects.bulk_create(
            [
                Party(
                    id=int(row["id"]),
                    partyid=row["partyid"] or "",
                    partyname=row["partyname"] or "",
                )
                for row in rows
            ]
        )

    def _import_polling_units(self, rows):
        PollingUnit.objects.bulk_create(
            [
                PollingUnit(
                    uniqueid=int(row["uniqueid"]),
                    polling_unit_id=int(row["polling_unit_id"]),
                    ward_id=int(row["ward_id"]),
                    lga_id=int(row["lga_id"]),
                    uniquewardid=int(row["uniquewardid"]) if row["uniquewardid"] else None,
                    polling_unit_number=row["polling_unit_number"],
                    polling_unit_name=row["polling_unit_name"],
                    polling_unit_description=row["polling_unit_description"],
                    lat=row["lat"],
                    long=row["long"],
                    entered_by_user=row["entered_by_user"],
                    date_entered=self._parse_datetime(row["date_entered"]),
                    user_ip_address=row["user_ip_address"],
                )
                for row in rows
            ]
        )

    def _import_announced_pu_results(self, rows):
        AnnouncedPUResult.objects.bulk_create(
            [
                AnnouncedPUResult(
                    result_id=int(row["result_id"]),
                    polling_unit_uniqueid=row["polling_unit_uniqueid"] or "",
                    party_abbreviation=row["party_abbreviation"] or "",
                    party_score=int(row["party_score"]),
                    entered_by_user=row["entered_by_user"] or "",
                    date_entered=self._parse_datetime(row["date_entered"]),
                    user_ip_address=row["user_ip_address"] or "",
                )
                for row in rows
            ]
        )

    def _import_announced_lga_results(self, rows):
        AnnouncedLGAResult.objects.bulk_create(
            [
                AnnouncedLGAResult(
                    result_id=int(row["result_id"]),
                    lga_name=row["lga_name"] or "",
                    party_abbreviation=row["party_abbreviation"] or "",
                    party_score=int(row["party_score"]),
                    entered_by_user=row["entered_by_user"] or "",
                    date_entered=self._parse_datetime(row["date_entered"]),
                    user_ip_address=row["user_ip_address"] or "",
                )
                for row in rows
            ]
        )
