# BincomDevCenter: Testing Guide

**Version**: 1.0 | **Last Updated**: April 3, 2026

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Test Suite Overview](#test-suite-overview)
3. [Running Tests](#running-tests)
4. [Understanding Test Results](#understanding-test-results)
5. [Writing New Tests](#writing-new-tests)
6. [Coverage Goals](#coverage-goals)
7. [CI/CD Testing](#cicd-testing)

---

## Quick Start

### Run All Tests
```bash
cd /Users/emmidev/Documents/BincomDevCenter
source .venv/bin/activate

# All tests
python manage.py test elections.tests

# Or with verbose output
python manage.py test elections.tests -v 2

# Or using pytest (if requirements-dev.txt installed)
pytest elections/tests.py -v
```

### Run Specific Test
```bash
# Single test class
python manage.py test elections.tests.ModelTests

# Single test method
python manage.py test elections.tests.StateModelTests.test_state_str_representation
```

### Run with Coverage Report
```bash
pip install -r requirements-dev.txt

# Generate coverage report
pytest elections/tests.py --cov=elections --cov-report=html

# View HTML report
open htmlcov/index.html
```

---

## Test Suite Overview

### Test Statistics
- **Total Tests**: 77
- **Test Classes**: 25
- **Coverage**: ~70% of elections app code
- **Execution Time**: ~6-7 seconds

### Test Categories

#### 1. Unit Tests: Models (8 test classes, ~15 tests)
Tests individual model functionality without external dependencies.

**Covered Models**:
- `State` — Country/region representation
- `LGA` — Local Government Area
- `Ward` — Administrative subdivision
- `PollingUnit` — Voting location
- `Party` — Political affiliates
- `AnnouncedPUResult` — Election results
- `AnnouncedLGAResult` — Aggregated results
- `SequenceCounter` — ID generation

**Example Tests**:
```python
def test_state_str_representation(self):
    """Test that State.__str__ returns the state name."""
    state = State.objects.get(state_id=25)
    self.assertEqual(str(state), "Delta")

def test_lga_ordering_by_name(self):
    """Test that LGAs are ordered by name."""
    lgas = list(LGA.objects.all().values_list("lga_name", flat=True))
    self.assertEqual(lgas, sorted(lgas))
```

**Files**: [elections/tests.py](elections/tests.py#L80-L240)

#### 2. Unit Tests: Services & Utilities (8 test classes, ~30 tests)
Tests business logic functions, querysets, and helper utilities.

**Covered Functions**:
- `ordered_parties()` — Get ordered party list
- `delta_lgas_queryset()` — Filter Delta State LGAs
- `displayable_polling_units_queryset()` — Get usable polling units
- `aggregate_party_scores()` — Sum and aggregate votes
- `normalize_party_code()` — Normalize party identifiers
- `party_label()` — Get display labels

**Example Tests**:
```python
def test_normalize_party_code_labour_to_labo(self):
    """Test that LABOUR is normalized to LABO."""
    self.assertEqual(normalize_party_code("LABOUR"), "LABO")

def test_delta_lgas_queryset_count_is_25(self):
    """Test that Delta State has 25 LGAs."""
    lgas = delta_lgas_queryset()
    self.assertEqual(lgas.count(), 25)
```

**Files**: [elections/tests.py](elections/tests.py#L243-L380)

#### 3. Unit Tests: Forms (4 test classes, ~10 tests)
Tests form initialization, validation, and data cleaning.

**Tested Form**:
- `PollingUnitSubmissionForm` — Create new polling units with results

**Example Tests**:
```python
def test_form_initialization_includes_party_fields(self):
    """Test that form includes party score fields."""
    form = PollingUnitSubmissionForm()
    party_fields = [f for f in form.fields if f.startswith("party_")]
    self.assertGreaterEqual(len(party_fields), 9)

def test_form_lga_queryset_is_delta_only(self):
    """Test that LGA field queryset includes only Delta State LGAs."""
    form = PollingUnitSubmissionForm()
    lga_field = form.fields["lga"]
    lgas = lga_field.queryset
    for lga in lgas:
        self.assertEqual(lga.state_id, DELTA_STATE_ID)
```

**Files**: [elections/tests.py](elections/tests.py#L383-430)

#### 4. Integration Tests: Views (5 test classes, ~12 tests)
Tests view functions, HTTP responses, and context data.

**Tested Views**:
- `dashboard()` — Homepage with summary stats
- `polling_unit_results()` — Result lookup view
- `lga_results()` — Aggregate LGA results
- `create_polling_unit()` — Submission form view
- `wards_api()` — JSON API for chained selectors
- `polling_units_api()` — JSON API for polling units

**Example Tests**:
```python
def test_polling_unit_results_view_requires_no_params(self):
    """Test that polling_unit_results view loads without query params."""
    response = self.client.get(reverse("elections:polling-unit-results"))
    self.assertEqual(response.status_code, 200)

def test_dashboard_summary_lga_count_is_25(self):
    """Test that dashboard shows 25 LGAs."""
    response = self.client.get(reverse("elections:dashboard"))
    summary = response.context.get("summary", {})
    self.assertEqual(summary["lga_count"], 25)
```

**Files**: [elections/tests.py](elections/tests.py#L433-550)

#### 5. Integration Tests: Workflows (3 test classes, ~5 tests)
Tests complete user workflows (multi-step interactions).

**Scenarios Tested**:
- Create a new polling unit and verify results are stored
- Submit form with optional fields (lat/long)
- Submit form with mixed zero/nonzero scores

**Example Tests**:
```python
def test_create_polling_unit_form_post_increments_sequence(self):
    """Test that creating a polling unit increments the polling_unit_id sequence."""
    before_next = SequenceCounter.objects.get(name="polling_unit_id").next_value
    
    # POST form data
    self.client.post(reverse("elections:polling-unit-create"), data={...})
    
    # Verify sequence incremented
    after_next = SequenceCounter.objects.get(name="polling_unit_id").next_value
    self.assertEqual(after_next, before_next + 1)
```

**Files**: [elections/tests.py](elections/tests.py#L553-620)

#### 6. Integration Tests: Management Commands (3 test classes, ~6 tests)
Tests Django management commands for data import and auditing.

**Tested Commands**:
- `import_bincom_sql` — Parse and load SQL dump
- `seed_demo_data` — Initialize demo data
- `audit_bincom_data` — Quality audit report

**Example Tests**:
```python
def test_import_bincom_sql_command_exists(self):
    """Test that import_bincom_sql management command exists and runs."""
    call_command("import_bincom_sql", verbosity=0)
    self.assertEqual(State.objects.count(), 37)

def test_audit_command_generates_valid_json(self):
    """Test that audit_bincom_data generates valid JSON."""
    with TemporaryDirectory() as tmpdir:
        output_path = f"{tmpdir}/report.json"
        call_command("audit_bincom_data", out=output_path, verbosity=0)
        report = json.loads(Path(output_path).read_text(encoding="utf-8"))
        self.assertIsInstance(report, dict)
```

**Files**: [elections/tests.py](elections/tests.py#L623-680)

#### 7. Analytics Tests (CONDITIONAL - requires analytics stack)
Tests clustering, feature engineering, and ML pipeline.

**Requirements**: `pip install -r requirements-analytics.txt`

**Tested Functions**:
- `load_election_frames()` — Load election data into pandas
- `build_completeness_table()` — Coverage analysis
- `build_modeling_dataset()` — Feature engineering
- `get_feature_columns()` — Feature extraction
- `evaluate_clustering_options()` — Clustering metrics
- `fit_final_clustering()` — Final model training

**Example Tests**:
```python
@skipUnless(ANALYTICS_STACK_AVAILABLE, "Analytics dependencies...")
def test_build_modeling_dataset_has_correct_lga_count(self):
    """Test that modeling dataset includes only result-backed LGAs."""
    frames = load_election_frames("db.sqlite3")
    modeling = build_modeling_dataset(frames)
    self.assertEqual(modeling.shape[0], 8)  # 8 result-backed LGAs
```

**Files**: [elections/tests.py](elections/tests.py#L683-750)

---

## Running Tests

### Basic Usage

#### Run All Tests
```bash
python manage.py test elections.tests
```

Output:
```
Found 77 test(s).
System check identified no issues...
...........  (78 dots = 78 passed)

Ran 77 tests in 6.234s
OK
```

#### Run with Verbose Output
```bash
python manage.py test elections.tests -v 2
```

Output:
```
test_state_str_representation (elections.tests.StateModelTests) ... ok
test_lga_ordering_by_name (elections.tests.LGAModelTests) ... ok
...
Ran 77 tests in 6.234s
OK
```

#### Run Single Test Class
```bash
python manage.py test elections.tests.PollingUnitModelTests
```

#### Run Single Test Method
```bash
python manage.py test elections.tests.PollingUnitModelTests.test_displayable_polling_units_excludes_placeholders
```

### Advanced Usage

#### Run Tests with Coverage
```bash
pip install -r requirements-dev.txt
pytest elections/tests.py --cov=elections --cov-report=html --cov-threshold=60
```

#### Run Tests with Fail-Fast
```bash
python manage.py test elections.tests --failfast
# Stops at first failure
```

#### Run Tests Excluding Analytics
```bash
python manage.py test elections.tests -k "not Analytics"
```

#### Run Tests Matching Pattern
```bash
python manage.py test elections.tests.FormTests
# Runs all tests in FormTests class
```

---

## Understanding Test Results

### Successful Run
```
Ran 77 tests in 6.234s
OK
```
✅ All tests passed.

### Failed Run
```
FAILED (failures=1)
...
FAIL: test_placeholder_polling_units_exist (elections.tests.PollingUnitModelTests)
AssertionError: False is not true
```

❌ Check:
1. Which test failed (above)
2. Error message (usually shows exact assertion)
3. Local environment differences (DEBUG, database, etc.)
4. See [Troubleshooting](#troubleshooting) below

### Skipped Tests
```
Ran 77 tests in 6.234s
OK (skipped=4)
```

⚠️ Some tests were skipped (likely analytics tests if `requirements-analytics.txt` not installed). This is expected.

---

## Writing New Tests

### Template: Model Test
```python
class NewModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_my_feature(self):
        """Test description."""
        # Arrange
        obj = MyModel.objects.first()
        
        # Act
        result = obj.some_method()
        
        # Assert
        self.assertEqual(result, expected_value)
```

### Template: Service Function Test
```python
class MyServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_service_function(self):
        """Test description."""
        # Arrange
        input_data = [...]
        
        # Act
        result = my_service_function(input_data)
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(len(result), expected_count)
```

### Template: View Test
```python
class MyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("import_bincom_sql", verbosity=0)

    def test_view_loads(self):
        """Test that view loads successfully."""
        response = self.client.get(reverse("elections:my-view"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expected text")
```

### Common Assertions
```python
# Equality
self.assertEqual(value, expected)
self.assertNotEqual(value, unexpected)

# Boolean
self.assertTrue(condition)
self.assertFalse(condition)

# Membership
self.assertIn(item, collection)
self.assertNotIn(item, collection)

# Exceptions
with self.assertRaises(ValueError):
    function_that_raises()

# Queries
self.assertEqual(Model.objects.count(), 5)
self.assertTrue(Model.objects.filter(...).exists())

# HTTP
self.assertEqual(response.status_code, 200)
self.assertContains(response, "text in page")
self.assertTemplateUsed(response, "template.html")
```

---

## Coverage Goals

### Current Status
- **Elections App Coverage**: ~70%
- **Target Coverage**: 60%+ (pragmatic for existing codebase)

### Coverage Report
```bash
pytest elections/tests.py --cov=elections --cov-report=term-missing

# Output shows:
# elections/models.py          150     2    99%
# elections/views.py           200    45    77%
# elections/services.py        120    15    87%
# elections/forms.py            80    20    75%
# ...
# TOTAL                        1000   250   75%
```

### Areas with Good Coverage
- ✅ Models (95%+)
- ✅ Services (80%+)
- ✅ Source quirks (100%)
- ✅ Validation logic (85%+)

### Areas with Low Coverage
- ⚠️ Views (77%) — Template rendering hard to test
- ⚠️ Admin (20%) — Optional; can test manually
- ⚠️ Edge cases — Add as issues reported

---

## CI/CD Testing

### GitHub Actions Workflow

Every push to `main` or PR triggers automatic tests:

```yaml
# .github/workflows/test-and-lint.yml
- Runs: Ubuntu 3.10
- Installs: Python + dev dependencies
- Steps:
  1. Lint with ruff
  2. Format check with black
  3. Run pytest with coverage
  4. Report results
```

### Viewing CI Results
1. Go to GitHub repo
2. Click **"Actions"** tab
3. Select latest workflow run
4. See detailed logs

### Test Failure in CI
- Red ❌ badge on PR
- Can't merge until tests pass
- Click details to see error logs
- Fix locally, push again

---

## Troubleshooting

### Test Fails Locally but Passes in CI

**Cause**: Database state or ENV variable difference
**Fix**:
```bash
# Reset test database
rm db.sqlite3
python manage.py migrate
python manage.py seed_demo_data

# Run tests again
python manage.py test elections.tests
```

### Import Errors in Tests

**Cause**: Missing dependencies or PYTHONPATH issue
**Fix**:
```bash
# Reinstall dev dependencies
pip install -r requirements-dev.txt

# Verify PYTHONPATH
echo $PYTHONPATH
python -c "import elections; print(elections)"
```

### Analytics Tests Skip

**Cause**: `requirements-analytics.txt` not installed
**Fix**:
```bash
pip install -r requirements-analytics.txt
python manage.py test elections.tests
# Should now run analytics tests
```

### Slow Tests

**Cause**: Database queries or imports
**Fix**:
```bash
# Run with timing info
pytest elections/tests.py -v --durations=10

# Takes > 1 second per test: may need optimization
```

---

## References

- [Django Testing Documentation](https://docs.djangoproject.com/en/5.2/topics/testing/)
- [pytest Documentation](https://pytest.org/en/latest/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [Best Practices](https://docs.djangoproject.com/en/5.2/topics/testing/overview/#best-practices)

---

**Last Reviewed**: April 3, 2026  
**Next Review**: After adding new features
