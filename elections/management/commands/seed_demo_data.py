from django.core.management import BaseCommand, call_command

from elections.models import AnnouncedLGAResult, AnnouncedPUResult, LGA, Party, PollingUnit, State, Ward


class Command(BaseCommand):
    help = (
        "Seed the Bincom demo dataset only when the database is empty, "
        "unless --force is provided."
    )

    def add_arguments(self, parser):
        parser.add_argument("--path", default="bincom_test.sql", help="Path to the SQL dump file.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force a full reseed even when existing rows are present.",
        )

    def handle(self, *args, **options):
        sql_path = options["path"]
        force = options["force"]
        counts = self._core_counts()

        if not force and all(value > 0 for value in counts.values()):
            self.stdout.write(
                self.style.WARNING(
                    "Demo seed skipped because the database already contains imported Bincom data."
                )
            )
            return

        if force:
            self.stdout.write(self.style.WARNING("Force reseed requested; re-importing SQL dump."))
        else:
            self.stdout.write("Database is empty or incomplete; importing the Bincom demo dataset.")

        call_command("import_bincom_sql", path=sql_path)

    @staticmethod
    def _core_counts():
        return {
            "states": State.objects.count(),
            "lgas": LGA.objects.count(),
            "wards": Ward.objects.count(),
            "parties": Party.objects.count(),
            "polling_units": PollingUnit.objects.count(),
            "announced_pu_results": AnnouncedPUResult.objects.count(),
            "announced_lga_results": AnnouncedLGAResult.objects.count(),
        }
