# ExecPlan: Bincom Election ML Submission (Notebook + Scripts, Clustering-First)

## Summary
Implement a self-contained machine learning submission centered on **clustering Delta State LGAs that have actual announced polling-unit results**, while separately analyzing **coverage across all 25 LGAs**. The user-visible outcome is:
1. a completed [`ML_Submission_Template.ipynb`](/Users/emmidev/Documents/BincomDevCenter/ML_Submission_Template.ipynb) with clear markdown, commented code, plots, hypotheses, model selection, evaluation, and conclusion;
2. small reusable helper scripts for dataset preparation and export;
3. reproducible outputs that a reviewer can regenerate from the repo with the existing SQLite database and analytics stack.

“EDA” means **exploratory data analysis**: inspecting the data, distributions, relationships, missingness, and anomalies before modeling.  
“Clustering” means **grouping similar LGAs without a predefined target label**.  
“Feature engineering” means **creating model-ready numerical columns from raw election data**.

## Decision Log
- No `PLANS.md` exists anywhere under `/Users/emmidev/Documents`, so this ExecPlan is the authoritative specification.
- Deliverable shape is **Notebook + scripts**, not notebook-only and not Django integration.
- Primary modeling goal is **clustering first**. There will be no forced supervised model unless later explicitly requested.
- Clustering population is **result-backed LGAs only**. All 25 LGAs will still appear in a separate completeness and polling-unit-distribution analysis.
- Primary clustering method is **hierarchical agglomerative clustering** because the usable modeling sample is very small (8 LGAs with announced polling-unit results), and hierarchical clustering is easier to interpret on small datasets.
- **K-means** will be used only as a supporting diagnostic for elbow and silhouette comparison, not as the final required model unless it clearly outperforms hierarchical clustering on stability and interpretability.
- Primary scaler is **StandardScaler** because clustering uses distances and the engineered features are on different numeric scales. **MinMaxScaler** will be used only as a sensitivity check if needed.
- Outliers will be **detected and discussed, not automatically removed**. If one feature dominates clustering distances, the notebook may compare raw vs winsorized or transformed variants and document the choice.

## Implementation Changes
### 1. Build the modeling dataset and reusable helpers
- Add one helper module under `scripts/` that:
  - loads data from `db.sqlite3` or the imported SQL-backed Django SQLite database;
  - builds an **LGA-level feature table** from `announced_pu_results`, `polling_unit`, `ward`, and `lga`;
  - exports a reproducible CSV such as `analysis_outputs/lga_modeling_dataset.csv`.
- Reuse or extend the existing descriptive exporter in [`scripts/analyze_election_data.py`](/Users/emmidev/Documents/BincomDevCenter/scripts/analyze_election_data.py) instead of duplicating raw SQL logic in many notebook cells.
- Define the modeling dataset to include, at minimum:
  - `lga_id`, `lga_name`
  - `polling_units_with_results`
  - `polling_units_with_metadata`
  - `coverage_pct`
  - total votes summed across all parties
  - one column per party vote share
  - dominant party share
  - vote dispersion feature
  - simple competitiveness feature such as top-party minus second-party share
- Keep all feature definitions explicit in notebook markdown, with plain-language explanations.

### 2. Complete the notebook as the primary submission artifact
- Fill the generic template in [`ML_Submission_Template.ipynb`](/Users/emmidev/Documents/BincomDevCenter/ML_Submission_Template.ipynb) with Bincom-specific content, not placeholder text.
- Structure the notebook around these sections in this exact order:
  1. Project summary and problem framing
  2. Understanding the election dataset and why only 8 LGAs are cluster-eligible
  3. Data loading and schema overview
  4. Data quality checks
  5. EDA on all 25 LGAs
  6. EDA on result-backed LGAs
  7. Feature engineering
  8. Preprocessing and scaling comparison
  9. Clustering model selection
  10. Cluster visualization and interpretation
  11. Strategy brief for each cluster
  12. Final conclusion and limitations
- Notebook cells should remain modular by calling helper functions where repeated logic exists. Avoid burying long SQL strings and repeated transformations in many cells.
- Every important chart must be followed by a short markdown interpretation answering “what does this mean for the election problem?”

### 3. Required analysis content
- Cover the user’s requested themes directly:
  - distribution of polling units across LGA
  - how many LGAs exist and how many have usable announced polling-unit results
  - missing values and missing-result coverage
  - feature encoding discussion
  - feature scaling comparison
  - outlier review
  - most-voted LGA grouped summaries
  - relationship visualizations
  - assumptions and business insights
  - strategy recommendations for each cluster
- Add these extra high-value EDA ideas:
  - party share heatmap by LGA
  - coverage vs total-vote scatter
  - dominant-party ranking across LGAs
  - clustering feature correlation heatmap
  - PCA 2D projection for cluster visualization
  - cluster profile table with plain-language labels such as “high-volume competitive LGAs” or “low-volume dominant-party LGAs”
- Treat “prediction and evaluation metrics” as **clustering validation**, not forced supervised prediction. Use:
  - silhouette score
  - Calinski-Harabasz score
  - Davies-Bouldin score
  - dendrogram inspection
  - elbow chart from K-means as a supporting comparison
- Final chosen clustering approach:
  - standardize numeric features;
  - compare `k=2` through `k=4`;
  - use hierarchical clustering as default final model;
  - only switch final model if another method is materially more interpretable and better-scoring.

### 4. Data handling rules
- For the **all-25-LGA descriptive analysis**, do not silently treat missing election results as real zero votes. Mark them as “no announced polling-unit results available”.
- For the **8-LGA clustering dataset**, only include LGAs with real announced polling-unit rows.
- Normalize party labels consistently so `LABOUR` and `LABO` are treated as the same party everywhere.
- Keep count-like completeness fields numeric and keep vote-share fields as proportions or percentages, not both mixed together in the same model input.
- Do not remove outliers by default. If any transformation is applied, show before/after impact and explain why.

## Test Plan and Acceptance Criteria
- Reproducibility steps must work from a fresh environment:
  1. `pip install -r requirements-analytics.txt`
  2. `python manage.py migrate`
  3. `python manage.py import_bincom_sql`
  4. run the helper script(s) that generate analysis outputs
  5. run notebook top-to-bottom without manual edits
- Acceptance checks:
  - notebook executes end-to-end without placeholder sections remaining;
  - notebook clearly states there are 25 Delta LGAs and 8 result-backed LGAs used for clustering;
  - clustering section includes feature table, scaler choice, elbow/dendrogram evidence, chosen cluster count, and validation metrics;
  - final section gives strategy recommendations for every produced cluster;
  - helper scripts regenerate the modeling dataset and descriptive CSV outputs deterministically;
  - existing Django app checks still pass if touched indirectly: `python manage.py check` and `python manage.py test elections`.
- Add or update tests only for reusable Python helpers, not for notebook cells directly. Notebook correctness is verified by successful execution and artifact outputs.

## Assumptions and Defaults
- The implementation will not modify the Django product surface unless absolutely necessary for data access; this plan is for the ML submission artifact, not new web features.
- The final notebook will use the existing SQLite database as the source of truth, not a manually copied CSV.
- The modeling unit is **LGA**, not polling unit.
- Because the cluster sample is very small, conclusions must be presented as **decision support**, not high-confidence scientific claims.
- If a section of the generic notebook template is irrelevant to unsupervised learning, adapt the heading but keep the submission coherent and explicitly explain the adaptation.
