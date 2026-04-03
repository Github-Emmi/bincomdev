from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from scripts.election_ml_pipeline import (
    RESULT_BACKED_LGA_IDS,
    build_completeness_table,
    build_modeling_dataset,
    evaluate_clustering_options,
    fit_final_clustering,
    get_feature_columns,
    load_election_frames,
)
from .models import (
    AnnouncedLGAResult,
    AnnouncedPUResult,
    LGA,
    Party,
    PollingUnit,
    SequenceCounter,
    State,
    Ward,
)
from .source_quirks import normalize_announced_lga_key, normalize_party_code


class ElectionViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_import_command_loads_expected_counts(self):
        self.assertEqual(State.objects.count(), 37)
        self.assertEqual(LGA.objects.count(), 25)
        self.assertEqual(Ward.objects.count(), 263)
        self.assertEqual(PollingUnit.objects.count(), 272)
        self.assertEqual(Party.objects.count(), 9)
        self.assertEqual(AnnouncedPUResult.objects.count(), 150)
        self.assertEqual(AnnouncedLGAResult.objects.count(), 225)
        self.assertEqual(
            SequenceCounter.objects.get(name="polling_unit_id").next_value,
            (PollingUnit.objects.order_by("-polling_unit_id").first().polling_unit_id + 1),
        )

    def test_dashboard_loads(self):
        response = self.client.get(reverse("elections:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bincom Election Result Explorer")

    def test_lga_results_page_loads(self):
        response = self.client.get(reverse("elections:lga-results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summed LGA Result")

    def test_wards_api_returns_ward_options_for_lga(self):
        response = self.client.get(reverse("elections:wards-api"), {"lga_id": 22})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item["id"] == 223 for item in payload["items"]))

    def test_polling_units_api_can_filter_to_result_backed_units(self):
        response = self.client.get(
            reverse("elections:polling-units-api"),
            {"lga_id": 22, "ward_id": 223, "with_results": 1},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["items"])

    def test_source_quirks_normalize_codes(self):
        self.assertEqual(normalize_party_code("LABOUR"), "LABO")
        self.assertEqual(normalize_announced_lga_key(22), "22")

    def test_can_create_new_polling_unit_submission(self):
        before_units = PollingUnit.objects.count()
        before_results = AnnouncedPUResult.objects.count()
        before_next_polling_unit_id = SequenceCounter.objects.get(name="polling_unit_id").next_value

        response = self.client.post(
            reverse("elections:polling-unit-create"),
            data={
                "lga": 22,
                "ward": 223,
                "polling_unit_number": "DT2201999",
                "polling_unit_name": "Assessment Test Unit",
                "polling_unit_description": "Created during automated testing",
                "lat": "5.123",
                "long": "6.456",
                "entered_by_user": "Codex Test",
                "party_PDP": 10,
                "party_DPP": 20,
                "party_ACN": 30,
                "party_PPA": 40,
                "party_CDC": 50,
                "party_JP": 60,
                "party_ANPP": 70,
                "party_LABO": 80,
                "party_CPP": 90,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PollingUnit.objects.count(), before_units + 1)
        self.assertEqual(AnnouncedPUResult.objects.count(), before_results + 9)
        self.assertEqual(
            SequenceCounter.objects.get(name="polling_unit_id").next_value,
            before_next_polling_unit_id + 1,
        )

    def test_ml_pipeline_builds_expected_result_backed_lgas(self):
        frames = load_election_frames("db.sqlite3")
        completeness = build_completeness_table(frames)
        modeling = build_modeling_dataset(frames)
        self.assertEqual(completeness.shape[0], 25)
        self.assertEqual(modeling.shape[0], 8)
        self.assertEqual(sorted(modeling["lga_id"].tolist()), RESULT_BACKED_LGA_IDS)

    def test_ml_pipeline_clustering_outputs_are_valid(self):
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        feature_columns = get_feature_columns(modeling)
        evaluation = evaluate_clustering_options(modeling, feature_columns)
        clustered, _ = fit_final_clustering(modeling, feature_columns)
        self.assertEqual(set(evaluation["k"].tolist()), {2, 3, 4})
        self.assertIn("hierarchical_ward", set(evaluation["method"].tolist()))
        self.assertEqual(clustered["cluster_id"].nunique(), 3)
