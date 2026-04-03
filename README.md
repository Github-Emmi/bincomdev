# Bincom Election Explorer

This Django solution answers the Bincom assessment using the provided `bincom_test.sql` dump as the source of truth.

## What it covers

1. Individual polling unit result page with chained LGA, ward, and polling unit selectors.
2. Summed LGA result page that computes totals from polling unit results only.
3. New polling unit submission page that stores scores for all parties in one action.

## Folder analysis summary

- The workspace originally contained only one file: `bincom_test.sql`.
- The dump includes Delta State election data across `states`, `lga`, `ward`, `polling_unit`, `party`, `announced_pu_results`, and `announced_lga_results`.
- There are 25 Delta LGAs, 263 wards, 272 polling unit rows, and 150 announced polling unit result rows.
- Only a subset of polling units have announced results, and many polling unit rows are placeholders with empty identifiers.
- The party table uses `LABOUR`, while the result rows use `LABO`; the app normalizes that mismatch.

## Architecture step-by-step

1. Create Django models that mirror the supplied SQL schema.
2. Build a custom management command to parse MySQL-style `INSERT INTO` blocks from `bincom_test.sql`.
3. Import the SQL dump into SQLite so the app can run locally and on Render without needing MySQL.
4. Filter selector options to usable Delta State polling units and announced-result records.
5. Render the three required pages with responsive templates and chained combo-box behavior.
6. Prepare deployment with `gunicorn`, WhiteNoise, static collection, and a `render.yaml`.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py import_bincom_sql
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Analytics stack

If you want the environment ready for data analysis, notebooks, and lightweight ML experiments as well, install:

```bash
pip install -r requirements-analytics.txt
```

This keeps Render deployment lean by leaving the web app runtime in `requirements.txt` and the heavier analysis stack in `requirements-analytics.txt`.

To export quick analysis tables from the imported SQLite database:

```bash
python scripts/analyze_election_data.py
```

This writes CSV summaries into `analysis_outputs/`.

## Deployment note

`render.yaml` is included for Render deployment. The build step installs dependencies, runs migrations, imports `bincom_test.sql`, and collects static files automatically.
