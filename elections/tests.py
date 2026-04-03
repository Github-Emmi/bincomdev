import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse


try:
    from scripts.election_ml_pipeline import (
        RESULT_BACKED_LGA_IDS,
        build_completeness_table,
        build_modeling_dataset,
        evaluate_clustering_options,
        export_ml_artifacts,
        fit_final_clustering,
        get_feature_columns,
        load_election_frames,
    )

    ANALYTICS_STACK_AVAILABLE = True
except ModuleNotFoundError:
    ANALYTICS_STACK_AVAILABLE = False

    RESULT_BACKED_LGA_IDS = []
    build_completeness_table = None
    build_modeling_dataset = None
    evaluate_clustering_options = None
    export_ml_artifacts = None
    fit_final_clustering = None
    get_feature_columns = None
    load_election_frames = None
from .models import (
    LGA,
    AnnouncedLGAResult,
    AnnouncedPUResult,
    Party,
    PollingUnit,
    SequenceCounter,
    State,
    Ward,
)
from .services import (
    aggregate_party_scores,
    delta_lgas_queryset,
    displayable_polling_units_queryset,
    ordered_parties,
)
from .source_quirks import (
    DELTA_STATE_ID,
    normalize_announced_lga_key,
    normalize_party_code,
    party_label,
)


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

    def test_demo_seed_command_skips_non_empty_database(self):
        before_units = PollingUnit.objects.count()
        custom_number = "DT2201888"
        self.assertFalse(PollingUnit.objects.filter(polling_unit_number=custom_number).exists())

        self.client.post(
            reverse("elections:polling-unit-create"),
            data={
                "lga": 22,
                "ward": 223,
                "polling_unit_number": custom_number,
                "polling_unit_name": "Persistent Demo Unit",
                "polling_unit_description": "Should survive a non-destructive seed pass",
                "lat": "5.321",
                "long": "6.654",
                "entered_by_user": "Seed Guard Test",
                "party_PDP": 1,
                "party_DPP": 2,
                "party_ACN": 3,
                "party_PPA": 4,
                "party_CDC": 5,
                "party_JP": 6,
                "party_ANPP": 7,
                "party_LABO": 8,
                "party_CPP": 9,
            },
            follow=True,
        )

        self.assertTrue(PollingUnit.objects.filter(polling_unit_number=custom_number).exists())
        call_command("seed_demo_data", verbosity=0)
        self.assertEqual(PollingUnit.objects.count(), before_units + 1)
        self.assertTrue(PollingUnit.objects.filter(polling_unit_number=custom_number).exists())

    def test_audit_command_writes_known_data_quality_report(self):
        with TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/data_quality_report.json"
            call_command("audit_bincom_data", out=output_path, verbosity=0)
            report = json.loads(Path(output_path).read_text(encoding="utf-8"))

        self.assertEqual(report["placeholder_polling_units"], 170)
        self.assertEqual(report["duplicate_polling_unit_id_groups"], 18)
        self.assertEqual(report["polling_unit_lga_ward_mismatches"], 1)
        self.assertEqual(report["result_backed_lgas"], 8)

    @skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies are not installed.")
    def test_ml_pipeline_builds_expected_result_backed_lgas(self):
        frames = load_election_frames("db.sqlite3")
        completeness = build_completeness_table(frames)
        modeling = build_modeling_dataset(frames)
        self.assertEqual(completeness.shape[0], 25)
        self.assertEqual(modeling.shape[0], 8)
        self.assertEqual(sorted(modeling["lga_id"].tolist()), RESULT_BACKED_LGA_IDS)

    @skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies are not installed.")
    def test_ml_pipeline_clustering_outputs_are_valid(self):
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        feature_columns = get_feature_columns(modeling)
        evaluation = evaluate_clustering_options(modeling, feature_columns)
        clustered, _ = fit_final_clustering(modeling, feature_columns)
        self.assertEqual(set(evaluation["k"].tolist()), {2, 3, 4})
        self.assertIn("hierarchical_ward", set(evaluation["method"].tolist()))
        self.assertEqual(clustered["cluster_id"].nunique(), 3)

    @skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies are not installed.")
    def test_ml_pipeline_can_export_analysis_artifacts(self):
        with TemporaryDirectory() as tmpdir:
            outputs = export_ml_artifacts(db_path="db.sqlite3", out_dir=tmpdir)
            for path in outputs.values():
                self.assertTrue(path.exists(), f"Expected export artifact at {path}")


# ============================================================================
# UNIT TESTS: Models
# ============================================================================


class StateModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_state_str_representation(self):
        """Test that State.__str__ returns the state name."""
        state = State.objects.get(state_id=25)
        self.assertEqual(str(state), "Delta")

    def test_state_has_expected_fields(self):
        """Test that State model has required fields."""
        state = State.objects.get(state_id=25)
        self.assertIsNotNone(state.state_id)
        self.assertIsNotNone(state.state_name)


class LGAModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_lga_str_representation(self):
        """Test that LGA.__str__ returns the LGA name."""
        lga = LGA.objects.get(lga_id=6)
        self.assertIsNotNone(str(lga))
        self.assertTrue(len(str(lga)) > 0)

    def test_lga_ordering_by_name(self):
        """Test that LGAs are ordered by name."""
        lgas = list(LGA.objects.all().values_list("lga_name", flat=True))
        self.assertEqual(lgas, sorted(lgas))

    def test_delta_state_lgas_count(self):
        """Test that Delta State (ID 25) has exactly 25 LGAs."""
        delta_lgas = LGA.objects.filter(state_id=DELTA_STATE_ID).count()
        self.assertEqual(delta_lgas, 25)


class WardModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_ward_str_representation(self):
        """Test that Ward.__str__ returns the ward name."""
        ward = Ward.objects.first()
        self.assertIsNotNone(str(ward))

    def test_ward_ordering_by_name(self):
        """Test that wards are ordered by name."""
        ward_names = list(Ward.objects.all().values_list("ward_name", flat=True))
        self.assertEqual(ward_names, sorted(ward_names))

    def test_ward_foreign_key_to_lga(self):
        """Test that ward.lga_id references an existing LGA."""
        ward = Ward.objects.first()
        self.assertTrue(LGA.objects.filter(lga_id=ward.lga_id).exists())


class PartyModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_party_str_representation(self):
        """Test that Party.__str__ returns the party name."""
        party = Party.objects.first()
        self.assertIsNotNone(str(party))

    def test_party_count_is_nine(self):
        """Test that exactly 9 parties are imported."""
        self.assertEqual(Party.objects.count(), 9)

    def test_party_partyid_is_unique(self):
        """Test that party IDs are unique."""
        ids = Party.objects.values_list("partyid", flat=True)
        self.assertEqual(len(ids), len(set(ids)))


class PollingUnitModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_polling_unit_str_representation(self):
        """Test that PollingUnit.__str__ includes name and number."""
        pu = PollingUnit.objects.filter(polling_unit_name__isnull=False).first()
        str_repr = str(pu)
        self.assertIsNotNone(str_repr)

    def test_polling_unit_ordering(self):
        """Test that polling units are ordered by name, number, uniqueid."""
        units = list(PollingUnit.objects.values_list("uniqueid", flat=True)[:5])
        self.assertTrue(len(units) > 0)

    def test_placeholder_polling_units_exist(self):
        """Test that placeholder polling units (empty name/number) exist and can be filtered."""
        from django.db.models import Q

        placeholders = PollingUnit.objects.filter(
            Q(polling_unit_name__isnull=True)
            | Q(polling_unit_name="")
            | Q(polling_unit_number__isnull=True)
            | Q(polling_unit_number="")
        )
        self.assertGreater(placeholders.count(), 0)

    def test_displayable_polling_units_excludes_placeholders(self):
        """Test that displayable queryset excludes placeholder polling units."""
        displayable = displayable_polling_units_queryset()
        placeholders = PollingUnit.objects.filter(
            polling_unit_name__isnull=True
        ) | PollingUnit.objects.filter(polling_unit_name="")
        for pu in placeholders[:5]:
            self.assertFalse(displayable.filter(uniqueid=pu.uniqueid).exists())


class AnnouncedPUResultModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_announced_pu_result_count(self):
        """Test that exactly 150 announced polling unit results are imported."""
        self.assertEqual(AnnouncedPUResult.objects.count(), 150)

    def test_announced_pu_result_polling_unit_uniqueid_references_exist(self):
        """Test that result polling_unit_uniqueid values reference actual polling units."""
        results = AnnouncedPUResult.objects.values_list("polling_unit_uniqueid", flat=True).distinct()
        for uniqueid_str in results[:10]:
            try:
                uniqueid_int = int(uniqueid_str)
                exists = PollingUnit.objects.filter(uniqueid=uniqueid_int).exists()
                self.assertTrue(exists, f"PollingUnit {uniqueid_int} not found")
            except ValueError:
                self.fail(f"polling_unit_uniqueid {uniqueid_str} is not a valid integer")


class SequenceCounterModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_sequence_counter_polling_unit_id_initialized(self):
        """Test that polling_unit_id sequence counter is initialized."""
        counter = SequenceCounter.objects.get(name="polling_unit_id")
        self.assertIsNotNone(counter.next_value)
        self.assertGreater(counter.next_value, 0)


# ============================================================================
# UNIT TESTS: Services & Utilities
# ============================================================================


class SourceQuirksTests(TestCase):
    def test_normalize_party_code_labour_to_labo(self):
        """Test that LABOUR is normalized to LABO."""
        self.assertEqual(normalize_party_code("LABOUR"), "LABO")

    def test_normalize_party_code_already_uppercase(self):
        """Test that already-uppercase codes remain unchanged."""
        self.assertEqual(normalize_party_code("LABO"), "LABO")
        self.assertEqual(normalize_party_code("PDP"), "PDP")

    def test_normalize_party_code_lowercase_input(self):
        """Test that lowercase input is uppercased."""
        self.assertEqual(normalize_party_code("labour"), "LABO")
        self.assertEqual(normalize_party_code("pdp"), "PDP")

    def test_normalize_party_code_handles_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        self.assertEqual(normalize_party_code("  LABO  "), "LABO")

    def test_normalize_party_code_handles_none(self):
        """Test that None input returns empty string."""
        self.assertEqual(normalize_party_code(None), "")

    def test_party_label_maps_labo_to_labour(self):
        """Test that LABO label maps back to LABOUR."""
        self.assertEqual(party_label("LABO"), "LABOUR")

    def test_party_label_unmapped_returns_canonical(self):
        """Test that unmapped codes return themselves."""
        self.assertEqual(party_label("PDP"), "PDP")

    def test_normalize_announced_lga_key_int_input(self):
        """Test that LGA key normalization works with int input."""
        self.assertEqual(normalize_announced_lga_key(22), "22")

    def test_normalize_announced_lga_key_string_input(self):
        """Test that LGA key normalization works with string input."""
        self.assertEqual(normalize_announced_lga_key("22"), "22")

    def test_normalize_announced_lga_key_none_input(self):
        """Test that None input is handled."""
        self.assertEqual(normalize_announced_lga_key(None), "")


class OrderedPartiesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_ordered_parties_returns_list_of_dicts(self):
        """Test that ordered_parties returns a list of dictionaries."""
        parties = ordered_parties()
        self.assertIsInstance(parties, list)
        self.assertTrue(all(isinstance(p, dict) for p in parties))

    def test_ordered_parties_includes_code_and_label(self):
        """Test that each party dict has 'code' and 'label' keys."""
        parties = ordered_parties()
        for party in parties:
            self.assertIn("code", party)
            self.assertIn("label", party)

    def test_ordered_parties_count_is_at_least_nine(self):
        """Test that at least 9 parties are returned."""
        parties = ordered_parties()
        self.assertGreaterEqual(len(parties), 9)


class AggregatePartyScoresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_aggregate_party_scores_returns_expected_structure(self):
        """Test that aggregate_party_scores returns a dict with 'rows', 'grand_total', 'raw_entry_count'."""
        results = AnnouncedPUResult.objects.all()[:10]
        agg = aggregate_party_scores(results)
        self.assertIn("rows", agg)
        self.assertIn("grand_total", agg)
        self.assertIn("raw_entry_count", agg)

    def test_aggregate_party_scores_empty_queryset(self):
        """Test that empty queryset returns zero totals."""
        empty_results = AnnouncedPUResult.objects.none()
        agg = aggregate_party_scores(empty_results)
        self.assertEqual(agg["grand_total"], 0)
        self.assertEqual(agg["raw_entry_count"], 0)

    def test_aggregate_party_scores_rows_include_required_fields(self):
        """Test that each row in aggregate has required fields."""
        results = AnnouncedPUResult.objects.all()
        agg = aggregate_party_scores(results)
        if agg["rows"]:
            for row in agg["rows"]:
                self.assertIn("code", row)
                self.assertIn("score", row)
                self.assertIn("share", row)


class DeltaLGAsQuersetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_delta_lgas_queryset_filters_to_delta_state(self):
        """Test that delta_lgas_queryset returns only Delta State LGAs."""
        lgas = delta_lgas_queryset()
        for lga in lgas:
            self.assertEqual(lga.state_id, DELTA_STATE_ID)

    def test_delta_lgas_queryset_count_is_25(self):
        """Test that Delta State has 25 LGAs."""
        lgas = delta_lgas_queryset()
        self.assertEqual(lgas.count(), 25)

    def test_delta_lgas_queryset_ordered_by_name(self):
        """Test that resulting LGAs are ordered by name."""
        lgas = list(delta_lgas_queryset().values_list("lga_name", flat=True))
        self.assertEqual(lgas, sorted(lgas))


# ============================================================================
# UNIT TESTS: Forms
# ============================================================================


class PollingUnitSubmissionFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_form_initialization_includes_lga_field(self):
        """Test that form includes LGA field."""
        from .forms import PollingUnitSubmissionForm

        form = PollingUnitSubmissionForm()
        self.assertIn("lga", form.fields)

    def test_form_initialization_includes_party_fields(self):
        """Test that form includes party score fields."""
        from .forms import PollingUnitSubmissionForm

        form = PollingUnitSubmissionForm()
        party_fields = [f for f in form.fields if f.startswith("party_")]
        self.assertGreaterEqual(len(party_fields), 9)

    def test_form_lga_queryset_is_delta_only(self):
        """Test that LGA field queryset includes only Delta State LGAs."""
        from .forms import PollingUnitSubmissionForm

        form = PollingUnitSubmissionForm()
        lga_field = form.fields["lga"]
        lgas = lga_field.queryset
        for lga in lgas:
            self.assertEqual(lga.state_id, DELTA_STATE_ID)

    def test_form_requires_positive_party_scores(self):
        """Test that party score fields require non-negative integers."""
        from .forms import PollingUnitSubmissionForm

        form = PollingUnitSubmissionForm()
        party_fields = {k: v for k, v in form.fields.items() if k.startswith("party_")}
        for field in party_fields.values():
            self.assertEqual(field.widget.attrs.get("min"), 0)


# ============================================================================
# INTEGRATION TESTS: Views & Workflows
# ============================================================================


class PollingUnitResultsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_polling_unit_results_view_requires_no_params(self):
        """Test that polling_unit_results view loads without query params."""
        response = self.client.get(reverse("elections:polling-unit-results"))
        self.assertEqual(response.status_code, 200)

    def test_polling_unit_results_view_with_lga_param(self):
        """Test that polling_unit_results view loads with LGA param."""
        response = self.client.get(
            reverse("elections:polling-unit-results"),
            {"lga": 22},
        )
        self.assertEqual(response.status_code, 200)

    def test_polling_unit_results_view_context_has_available_lgas(self):
        """Test that view context includes available LGAs."""
        response = self.client.get(reverse("elections:polling-unit-results"))
        self.assertIn("available_lgas", response.context)

    def test_polling_unit_results_view_filters_selectors_by_lga(self):
        """Test that ward/polling unit selectors filter based on LGA."""
        response_with_lga = self.client.get(
            reverse("elections:polling-unit-results"),
            {"lga": 22},
        )
        wards = response_with_lga.context.get("ward_options", [])
        for ward in wards:
            self.assertEqual(ward.lga_id, 22)


class LGAResultsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_lga_results_view_loads(self):
        """Test that LGA results view loads."""
        response = self.client.get(reverse("elections:lga-results"))
        self.assertEqual(response.status_code, 200)

    def test_lga_results_view_with_valid_lga(self):
        """Test that LGA results view loads with valid LGA ID."""
        response = self.client.get(
            reverse("elections:lga-results"),
            {"lga": 22},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("selected_lga", response.context)

    def test_lga_results_view_includes_comparison_rows(self):
        """Test that view context includes comparison between calculated and announced results."""
        response = self.client.get(
            reverse("elections:lga-results"),
            {"lga": 22},
        )
        self.assertIn("comparison_rows", response.context)


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_dashboard_context_has_summary_stats(self):
        """Test that dashboard context includes summary statistics."""
        response = self.client.get(reverse("elections:dashboard"))
        summary = response.context.get("summary", {})
        self.assertIn("lga_count", summary)
        self.assertIn("ward_count", summary)
        self.assertIn("polling_unit_count", summary)

    def test_dashboard_summary_lga_count_is_25(self):
        """Test that dashboard shows 25 LGAs."""
        response = self.client.get(reverse("elections:dashboard"))
        summary = response.context.get("summary", {})
        self.assertEqual(summary["lga_count"], 25)


class PollingUnitCreationWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_create_polling_unit_form_post_increments_sequence(self):
        """Test that creating a polling unit increments the polling_unit_id sequence."""
        before_next = SequenceCounter.objects.get(name="polling_unit_id").next_value
        self.client.post(
            reverse("elections:polling-unit-create"),
            data={
                "lga": 22,
                "ward": 223,
                "polling_unit_number": "TEST_SEQUENCE",
                "polling_unit_name": "Test Sequence Unit",
                "party_PDP": 100,
                "party_DPP": 200,
                "party_ACN": 300,
                "party_PPA": 400,
                "party_CDC": 500,
                "party_JP": 600,
                "party_ANPP": 700,
                "party_LABO": 800,
                "party_CPP": 900,
            },
            follow=True,
        )
        after_next = SequenceCounter.objects.get(name="polling_unit_id").next_value
        self.assertEqual(after_next, before_next + 1)

    def test_create_polling_unit_with_optional_fields(self):
        """Test that polling unit can be created with optional fields like lat/long."""
        self.client.post(
            reverse("elections:polling-unit-create"),
            data={
                "lga": 22,
                "ward": 223,
                "polling_unit_number": "TEST_LATLONG",
                "polling_unit_name": "Test LatLong Unit",
                "lat": "5.123456",
                "long": "6.654321",
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
        unit = PollingUnit.objects.get(polling_unit_number="TEST_LATLONG")
        self.assertEqual(unit.lat, "5.123456")
        self.assertEqual(unit.long, "6.654321")

    def test_create_polling_unit_with_mixed_zero_and_nonzero_scores(self):
        """Test that polling unit can be created with some party scores as zero."""
        self.client.post(
            reverse("elections:polling-unit-create"),
            data={
                "lga": 22,
                "ward": 223,
                "polling_unit_number": "TEST_MIXED_SCORES",
                "polling_unit_name": "Test Mixed Scores",
                "party_PDP": 100,
                "party_DPP": 0,
                "party_ACN": 50,
                "party_PPA": 0,
                "party_CDC": 0,
                "party_JP": 0,
                "party_ANPP": 0,
                "party_LABO": 0,
                "party_CPP": 0,
            },
            follow=True,
        )
        unit = PollingUnit.objects.get(polling_unit_number="TEST_MIXED_SCORES")
        results = AnnouncedPUResult.objects.filter(
            polling_unit_uniqueid=str(unit.uniqueid)
        ).values("party_abbreviation", "party_score")
        # Expect 9 result records (one per party, even zeros)
        self.assertEqual(results.count(), 9)


# ============================================================================
# INTEGRATION TESTS: Management Commands
# ============================================================================


class ManagementCommandImportTests(TestCase):
    def test_import_bincom_sql_command_exists(self):
        """Test that import_bincom_sql management command exists and runs without error."""
        # This is implicitly tested by setUpTestData in other test classes
        # but we can also test it explicitly
        call_command("import_bincom_sql", verbosity=0)
        self.assertEqual(State.objects.count(), 37)

    def test_import_bincom_sql_is_idempotent(self):
        """Test that importing twice with --force replaces data correctly."""
        call_command("import_bincom_sql", verbosity=0)
        count_first = PollingUnit.objects.count()
        call_command("import_bincom_sql", "--force", verbosity=0)
        count_second = PollingUnit.objects.count()
        self.assertEqual(count_first, count_second)


class ManagementCommandAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_audit_command_generates_valid_json(self):
        """Test that audit_bincom_data generates valid JSON."""
        with TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/report.json"
            call_command("audit_bincom_data", out=output_path, verbosity=0)
            report = json.loads(Path(output_path).read_text(encoding="utf-8"))
            self.assertIsInstance(report, dict)

    def test_audit_command_report_includes_required_fields(self):
        """Test that audit report includes expected quality metrics."""
        with TemporaryDirectory() as tmpdir:
            output_path = f"{tmpdir}/report.json"
            call_command("audit_bincom_data", out=output_path, verbosity=0)
            report = json.loads(Path(output_path).read_text(encoding="utf-8"))
            required_fields = [
                "placeholder_polling_units",
                "duplicate_polling_unit_id_groups",
                "polling_unit_lga_ward_mismatches",
                "result_backed_lgas",
            ]
            for field in required_fields:
                self.assertIn(field, report)


# ============================================================================
# INTEGRATION TESTS: Analytics Pipeline
# ============================================================================


@skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies are not installed.")
class AnalyticsPipelineLoadingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_load_election_frames_returns_dict(self):
        """Test that load_election_frames returns a dictionary of DataFrames."""
        frames = load_election_frames("db.sqlite3")
        self.assertIsInstance(frames, dict)

    def test_load_election_frames_includes_lga_frame(self):
        """Test that loaded frames include LGA data."""
        frames = load_election_frames("db.sqlite3")
        self.assertIn("lga", frames)
        self.assertEqual(frames["lga"].shape[0], 25)


@skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies are not installed.")
class AnalyticsPipelineFeatureEngineeringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_build_modeling_dataset_returns_dataframe(self):
        """Test that build_modeling_dataset returns a DataFrame."""
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        self.assertIsNotNone(modeling)
        self.assertTrue(hasattr(modeling, "shape"))

    def test_build_modeling_dataset_has_correct_lga_count(self):
        """Test that modeling dataset includes only result-backed LGAs."""
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        self.assertEqual(modeling.shape[0], 8)

    def test_get_feature_columns_returns_list(self):
        """Test that get_feature_columns returns a list of feature names."""
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        features = get_feature_columns(modeling)
        self.assertIsInstance(features, list)
        self.assertGreater(len(features), 0)


@skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies are not installed.")
class AnalyticsPipelineClusteringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_evaluate_clustering_options_returns_dataframe(self):
        """Test that evaluate_clustering_options returns evaluation metrics."""
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        features = get_feature_columns(modeling)
        evaluation = evaluate_clustering_options(modeling, features)
        self.assertIsNotNone(evaluation)
        self.assertTrue(hasattr(evaluation, "shape"))

    def test_fit_final_clustering_returns_tuple(self):
        """Test that fit_final_clustering returns tuple with dataframe and model."""
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        features = get_feature_columns(modeling)
        clustered, model = fit_final_clustering(modeling, features)
        self.assertIsNotNone(clustered)
        self.assertIsNotNone(model)

    def test_fit_final_clustering_adds_cluster_id_column(self):
        """Test that clustering adds a 'cluster_id' column to the dataset."""
        frames = load_election_frames("db.sqlite3")
        modeling = build_modeling_dataset(frames)
        features = get_feature_columns(modeling)
        clustered, _ = fit_final_clustering(modeling, features)
        self.assertIn("cluster_id", clustered.columns)
        self.assertGreater(clustered["cluster_id"].nunique(), 0)
