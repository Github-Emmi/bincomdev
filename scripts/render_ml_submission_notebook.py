#!/usr/bin/env python3
import sys
from pathlib import Path
from textwrap import dedent

import nbformat as nbf

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def md(text: str):
    return nbf.v4.new_markdown_cell(dedent(text).strip() + "\n")


def code(text: str):
    return nbf.v4.new_code_cell(dedent(text).strip() + "\n")


def build_notebook():
    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.14",
        },
    }

    cells = [
        md(
            """
            # Bincom Election ML Submission

            **Project Name:** Delta State Election Intelligence Segmentation  
            **Project Type:** Exploratory Data Analysis and Unsupervised Machine Learning  
            **Contribution:** Individual  
            **Primary Objective:** Cluster Delta State LGAs that have announced polling-unit results and turn the clusters into decision-support strategy briefs.
            """
        ),
        md(
            """
            ## Project Summary

            This submission investigates the 2011 Delta State election sample supplied in the Bincom assessment dataset. The underlying business question is not just who scored the most votes in absolute terms, but how different Local Government Areas (LGAs) behave when we compare turnout scale, party dominance, competitiveness, and result coverage. That matters because an election operations team, public policy unit, or local government analyst can use segmentation to decide where to defend strongholds, where to invest persuasion efforts, and where to improve polling-unit reporting quality.

            The dataset contains all 25 Delta State LGAs, 263 wards, 272 polling-unit rows, and announced polling-unit results for only a subset of polling units. A key modeling constraint is that only **8 LGAs** have real announced polling-unit result rows. Because clustering needs actual numeric behavior rather than missing-result placeholders, the clustering model is built only on those 8 result-backed LGAs. The full set of 25 LGAs is still analyzed descriptively so that missing-result coverage and data completeness are not hidden.

            The workflow in this notebook follows a practical machine learning process. First, the raw SQLite data is loaded from the project database rather than from a manually copied CSV. Next, the notebook checks data quality and quantifies how many LGAs have usable announced polling-unit results. Then it performs exploratory analysis on the full Delta State population and on the result-backed subset. Feature engineering converts party-level vote totals into LGA-level behavioral signals such as party vote shares, dominant-party share, competitiveness margin, vote dispersion, and coverage percentage. These features are scaled and compared with both StandardScaler and MinMaxScaler because clustering depends on feature distances.

            For the model itself, this submission treats clustering as the correct “prediction” task. Instead of predicting a target label that the dataset does not provide, the notebook groups LGAs with similar election behavior using hierarchical agglomerative clustering as the preferred method, while K-means is used as a supporting benchmark. The model is evaluated with internal clustering metrics: silhouette score, Calinski-Harabasz score, Davies-Bouldin score, plus elbow and dendrogram diagnostics. The final section translates cluster outputs into practical strategy briefs so the analysis ends with an actionable conclusion rather than only charts and tables.
            """
        ),
        md(
            """
            ## Problem Statement

            Bincom provided election results stored at polling-unit level, alongside LGA, ward, and polling-unit reference tables. The practical challenge is to understand:

            1. how polling units are distributed across Delta State LGAs;
            2. which LGAs actually have usable announced polling-unit results;
            3. how party behavior differs across result-backed LGAs; and
            4. whether LGAs can be segmented into meaningful groups for strategy and decision support.

            Because the source does not provide a clean supervised learning target, this notebook frames the machine learning problem as **unsupervised clustering** of result-backed LGAs.
            """
        ),
        md(
            """
            ## Reproducibility

            Run the following from the repository root before executing the notebook:

            ```bash
            pip install -r requirements-analytics.txt
            python manage.py migrate
            python manage.py import_bincom_sql
            python scripts/build_lga_modeling_dataset.py
            ```

            The notebook reads from `db.sqlite3`, regenerates CSV artifacts in `analysis_outputs/`, and can be executed top-to-bottom without manual editing.
            """
        ),
        md("## 1. Project Setup and Library Imports"),
        code(
            """
            import os
            import sys
            import warnings
            from pathlib import Path

            import matplotlib.pyplot as plt
            import numpy as np
            import pandas as pd
            import seaborn as sns
            from IPython.display import Markdown, display

            ROOT = Path.cwd()
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))

            os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")
            warnings.filterwarnings("ignore")

            from scripts.election_ml_pipeline import (
                PARTY_ORDER,
                build_cluster_profiles,
                build_completeness_table,
                build_dendrogram_linkage,
                build_lga_result_long,
                build_lga_summary,
                build_modeling_dataset,
                build_party_share_table,
                choose_final_clustering,
                evaluate_clustering_options,
                export_ml_artifacts,
                fit_final_clustering,
                get_feature_columns,
                load_election_frames,
                scale_features,
            )

            sns.set_theme(style="whitegrid", context="talk")
            plt.rcParams["figure.figsize"] = (12, 6)
            pd.set_option("display.max_columns", 200)
            pd.set_option("display.float_format", lambda value: f"{value:,.4f}")
            """
        ),
        code(
            """
            output_paths = export_ml_artifacts(db_path="db.sqlite3", out_dir="analysis_outputs")
            frames = load_election_frames("db.sqlite3")
            completeness_df = build_completeness_table(frames)
            result_long_df = build_lga_result_long(frames)
            lga_summary_df = build_lga_summary(frames)
            party_share_df = build_party_share_table(frames)
            modeling_df = build_modeling_dataset(frames)
            feature_columns = get_feature_columns(modeling_df)
            scaled_feature_sets = scale_features(modeling_df, feature_columns)
            evaluation_df = evaluate_clustering_options(modeling_df, feature_columns)
            clustered_df, evaluation_df = fit_final_clustering(modeling_df, feature_columns)
            cluster_profiles_df = build_cluster_profiles(clustered_df, feature_columns)
            final_method, final_k = choose_final_clustering(evaluation_df)

            print("Artifacts written:")
            for name, path in output_paths.items():
                print(f"- {name}: {path}")
            print(f"Final clustering choice: {final_method} with k={final_k}")
            """
        ),
        md("## 2. Understanding the Election Dataset and Why Only 8 LGAs Are Cluster-Eligible"),
        code(
            """
            dataset_overview = pd.DataFrame(
                [
                    {"metric": "Delta State LGAs", "value": completeness_df.shape[0]},
                    {"metric": "Wards", "value": frames["ward"].shape[0]},
                    {"metric": "Polling unit rows", "value": frames["polling_unit"].shape[0]},
                    {"metric": "Usable polling units", "value": int(completeness_df["polling_units_with_metadata"].sum())},
                    {"metric": "Result-backed LGAs", "value": modeling_df.shape[0]},
                    {"metric": "Announced polling-unit result rows", "value": frames["announced_pu_results"].shape[0]},
                ]
            )
            display(dataset_overview)

            display(
                modeling_df[
                    ["lga_id", "lga_name", "polling_units_with_results", "coverage_pct", "total_votes", "dominant_party"]
                ].sort_values("total_votes", ascending=False)
            )
            """
        ),
        md(
            """
            The full Delta State reference data contains **25 LGAs**, but only **8 LGAs** have announced polling-unit result rows that can support clustering. That is why the notebook treats the 25-LGA population as a descriptive analysis problem, while the clustering model is restricted to the 8 result-backed LGAs.
            """
        ),
        md("## 3. Data Loading and Schema Overview"),
        code(
            """
            schema_overview = pd.DataFrame(
                [
                    {"table": name, "rows": frame.shape[0], "columns": ", ".join(frame.columns[:8])}
                    for name, frame in frames.items()
                ]
            )
            display(schema_overview)
            display(frames["lga"].head())
            display(frames["polling_unit"].head())
            display(frames["announced_pu_results"].head())
            """
        ),
        md("## 4. Data Quality Checks"),
        code(
            """
            missing_summary = pd.DataFrame(
                [
                    {
                        "table": name,
                        "column": column,
                        "missing_values": int(frame[column].isna().sum()),
                    }
                    for name, frame in frames.items()
                    for column in frame.columns
                ]
            )
            display(missing_summary.loc[missing_summary["missing_values"] > 0].sort_values(["table", "missing_values"], ascending=[True, False]).head(20))

            no_result_lgas = completeness_df.loc[
                completeness_df["polling_units_with_results"] == 0,
                ["lga_name", "polling_units_with_metadata", "result_status"],
            ].sort_values("polling_units_with_metadata", ascending=False)
            display(no_result_lgas.head(10))
            """
        ),
        md(
            """
            Missingness in this project is not only about blank cells. A more important issue is **missing election coverage**: many LGAs have usable polling-unit metadata but no announced polling-unit result rows. Those LGAs are retained for descriptive analysis but excluded from clustering so the model does not confuse “no result was recorded” with “zero votes were cast”.
            """
        ),
        md("## 5. EDA on All 25 LGAs"),
        code(
            """
            fig, axes = plt.subplots(1, 2, figsize=(18, 6))

            completeness_plot = completeness_df.sort_values("polling_units_with_metadata", ascending=False)
            sns.barplot(
                data=completeness_plot,
                x="polling_units_with_metadata",
                y="lga_name",
                color="#2a9d8f",
                ax=axes[0],
            )
            axes[0].set_title("Distribution of usable polling units across LGAs")
            axes[0].set_xlabel("Usable polling units")
            axes[0].set_ylabel("LGA")

            coverage_plot = completeness_df.sort_values("coverage_pct", ascending=False)
            sns.barplot(
                data=coverage_plot,
                x="coverage_pct",
                y="lga_name",
                hue="result_status",
                dodge=False,
                palette=["#e76f51", "#264653"],
                ax=axes[1],
            )
            axes[1].set_title("Coverage of announced polling-unit results across LGAs")
            axes[1].set_xlabel("Coverage percentage")
            axes[1].set_ylabel("")
            axes[1].legend(title="")

            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            Two patterns stand out. First, the number of usable polling units is uneven across LGAs, so the descriptive population is not balanced. Second, announced polling-unit coverage is sparse: most LGAs have zero announced result coverage, which means any machine learning model that depends on vote behavior must be built on the smaller result-backed subset instead of the full 25-LGA reference list.
            """
        ),
        code(
            """
            fig, axes = plt.subplots(1, 2, figsize=(18, 5))

            sns.histplot(completeness_df["polling_units_with_metadata"], bins=10, kde=False, color="#457b9d", ax=axes[0])
            axes[0].set_title("Histogram of usable polling units per LGA")
            axes[0].set_xlabel("Usable polling units")

            sns.boxplot(data=completeness_df[["polling_units_with_metadata", "polling_units_with_results", "coverage_pct"]], ax=axes[1])
            axes[1].set_title("Outlier view for coverage-related descriptive features")
            axes[1].set_ylabel("Value")

            plt.tight_layout()
            plt.show()

            completeness_df.sort_values("polling_units_with_metadata", ascending=False).head(10)
            """
        ),
        md(
            """
            The coverage-related features have visible dispersion and some LGA-level extremes. At this stage the notebook only **observes** outliers; it does not delete them. That matches the project rule that unusual LGAs should be discussed before any transformation is considered.
            """
        ),
        md("## 6. EDA on Result-Backed LGAs"),
        code(
            """
            result_backed_summary = modeling_df[
                [
                    "lga_name",
                    "polling_units_with_results",
                    "coverage_pct",
                    "total_votes",
                    "dominant_party",
                    "dominant_party_share",
                    "competitiveness_margin",
                ]
            ].sort_values("total_votes", ascending=False)
            display(result_backed_summary)
            """
        ),
        code(
            """
            party_share_heatmap = modeling_df.set_index("lga_name")[[f"share_{party.lower()}" for party in PARTY_ORDER]]
            plt.figure(figsize=(14, 6))
            sns.heatmap(party_share_heatmap, cmap="YlGnBu", annot=True, fmt=".2f")
            plt.title("Party vote-share heatmap by result-backed LGA")
            plt.xlabel("Party share features")
            plt.ylabel("LGA")
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            The party-share heatmap shows that the result-backed LGAs are not interchangeable. Some LGAs are dominated by one party, while others have flatter share profiles. This is exactly the type of structure clustering is meant to capture.
            """
        ),
        code(
            """
            plt.figure(figsize=(12, 6))
            ax = sns.scatterplot(
                data=modeling_df,
                x="coverage_pct",
                y="total_votes",
                hue="dominant_party",
                s=180,
                palette="tab10",
            )
            for _, row in modeling_df.iterrows():
                ax.text(row["coverage_pct"] + 0.5, row["total_votes"] + 100, row["lga_name"], fontsize=10)
            plt.title("Coverage versus total votes for result-backed LGAs")
            plt.xlabel("Coverage percentage")
            plt.ylabel("Total announced votes")
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            Coverage and total votes do not move perfectly together. Uvwie and Ethiope West are high-volume LGAs, while Ika North - East has perfect coverage within a much smaller result base. That supports the idea that scale and reporting coverage should both be included as features.
            """
        ),
        code(
            """
            most_voted_lga = modeling_df.sort_values("total_votes", ascending=False)[["lga_name", "total_votes", "dominant_party"]]

            plt.figure(figsize=(12, 6))
            sns.barplot(data=most_voted_lga, x="total_votes", y="lga_name", hue="dominant_party", dodge=False, palette="Set2")
            plt.title("Most voted LGAs grouped by dominant party")
            plt.xlabel("Total announced votes")
            plt.ylabel("LGA")
            plt.tight_layout()
            plt.show()

            display(most_voted_lga)
            """
        ),
        md(
            """
            The most-voted LGAs are not all dominated by the same party. That matters for strategy because high-volume LGAs can be large opportunities or large risks depending on whether competition is narrow or one-sided.
            """
        ),
        code(
            """
            fig, axes = plt.subplots(1, 2, figsize=(16, 5))

            sns.boxplot(data=modeling_df[["total_votes", "coverage_pct", "dominant_party_share", "competitiveness_margin"]], ax=axes[0])
            axes[0].set_title("Outlier review for key modeling features")
            axes[0].tick_params(axis="x", rotation=20)

            sns.heatmap(modeling_df[feature_columns].corr(), cmap="coolwarm", center=0, ax=axes[1])
            axes[1].set_title("Feature relationship heatmap")

            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            The outlier review shows real variation in total votes and coverage, but no feature is removed automatically. The relationship heatmap also shows that some engineered variables overlap conceptually, which is expected because dominant-party share and competitiveness margin both describe concentration of support.
            """
        ),
        md("## 7. Feature Engineering"),
        code(
            """
            feature_definitions = pd.DataFrame(
                [
                    {"feature": "polling_units_with_results", "meaning": "How many usable polling units in the LGA have announced party scores."},
                    {"feature": "polling_units_with_metadata", "meaning": "How many usable polling units are listed for the LGA in the reference table."},
                    {"feature": "coverage_pct", "meaning": "Percentage of usable polling units that have announced results."},
                    {"feature": "total_votes", "meaning": "Sum of announced votes across all parties for the LGA."},
                    {"feature": "share_<party>", "meaning": "Vote share contributed by each party in the LGA."},
                    {"feature": "dominant_party_share", "meaning": "Largest party share in the LGA."},
                    {"feature": "competitiveness_margin", "meaning": "Difference between the top party share and the second party share."},
                    {"feature": "vote_dispersion", "meaning": "Spread of party shares within the LGA."},
                    {"feature": "effective_party_count", "meaning": "Compact measure of how fragmented the vote is across parties."},
                ]
            )
            display(feature_definitions)
            display(modeling_df[["lga_name", *feature_columns]].head())
            """
        ),
        md(
            """
            These engineered features convert raw party totals into behavior-oriented signals. The vote-share features describe party composition, while coverage, competitiveness, and dispersion describe the quality and structure of the electoral environment.
            """
        ),
        md("## 8. Preprocessing and Scaling Comparison"),
        code(
            """
            standard_scaled = scaled_feature_sets["standard"]
            minmax_scaled = scaled_feature_sets["minmax"]

            scaling_comparison = pd.DataFrame(
                {
                    "feature": feature_columns,
                    "raw_mean": modeling_df[feature_columns].mean().values,
                    "raw_std": modeling_df[feature_columns].std().values,
                    "standard_mean": standard_scaled.mean().values,
                    "standard_std": standard_scaled.std().values,
                    "minmax_min": minmax_scaled.min().values,
                    "minmax_max": minmax_scaled.max().values,
                }
            )
            display(scaling_comparison.round(4))
            """
        ),
        md(
            """
            StandardScaler is chosen for the final clustering workflow because the features have different numeric scales and clustering uses distance. Standard scaling centers each feature around zero and gives it comparable variance, while MinMaxScaler is kept as a sensitivity check rather than the default.
            """
        ),
        md("## 9. Clustering Model Selection"),
        code(
            """
            display(evaluation_df.round(4))
            """
        ),
        code(
            """
            fig, axes = plt.subplots(1, 2, figsize=(16, 5))

            kmeans_rows = evaluation_df.loc[evaluation_df["method"] == "kmeans"].sort_values("k")
            sns.lineplot(data=kmeans_rows, x="k", y="inertia", marker="o", ax=axes[0])
            axes[0].set_title("Elbow chart using K-means inertia")
            axes[0].set_xlabel("Number of clusters (k)")
            axes[0].set_ylabel("Inertia")

            sns.barplot(data=evaluation_df, x="k", y="silhouette_score", hue="method", ax=axes[1])
            axes[1].set_title("Silhouette score comparison")
            axes[1].set_xlabel("Number of clusters (k)")
            axes[1].set_ylabel("Silhouette score")

            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            The elbow chart provides a supporting K-means diagnostic, while the silhouette chart compares methods directly. In this dataset, both methods point toward the same practical region, and the final rule keeps hierarchical clustering as the default unless another method is clearly better and more interpretable.
            """
        ),
        code(
            """
            from scipy.cluster.hierarchy import dendrogram

            linkage_matrix = build_dendrogram_linkage(modeling_df, feature_columns)
            plt.figure(figsize=(14, 6))
            dendrogram(linkage_matrix, labels=modeling_df["lga_name"].tolist(), leaf_rotation=20)
            plt.title("Hierarchical clustering dendrogram")
            plt.xlabel("LGA")
            plt.ylabel("Ward linkage distance")
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            The dendrogram supports a three-cluster interpretation: one broad competitive cluster, one high-volume cluster, and one small but distinct high-coverage cluster. That is consistent with the internal validation scores, so the final solution uses a **3-cluster hierarchical model**.
            """
        ),
        md("## 10. Cluster Visualization and Interpretation"),
        code(
            """
            display(
                clustered_df[
                    [
                        "lga_name",
                        "cluster_id",
                        "final_method",
                        "final_k",
                        "dominant_party",
                        "total_votes",
                        "coverage_pct",
                        "competitiveness_margin",
                    ]
                ].sort_values(["cluster_id", "total_votes"], ascending=[True, False])
            )
            """
        ),
        code(
            """
            plt.figure(figsize=(12, 7))
            ax = sns.scatterplot(
                data=clustered_df,
                x="pca_1",
                y="pca_2",
                hue="cluster_id",
                style="dominant_party",
                s=220,
                palette="Set1",
            )
            for _, row in clustered_df.iterrows():
                ax.text(row["pca_1"] + 0.03, row["pca_2"] + 0.03, row["lga_name"], fontsize=10)
            plt.title("PCA projection of clustered LGAs")
            plt.xlabel("Principal component 1")
            plt.ylabel("Principal component 2")
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            The PCA view shows that the clusters are not random labels pasted onto the data. The LGAs separate in a way that matches differences in vote scale, coverage, and competitiveness. Because the sample size is only eight LGAs, the plot should be treated as decision support rather than a strong scientific proof.
            """
        ),
        code(
            """
            cluster_heatmap = clustered_df.groupby("cluster_id")[feature_columns].mean()
            plt.figure(figsize=(16, 6))
            sns.heatmap(cluster_heatmap, cmap="mako", annot=False)
            plt.title("Average feature intensity by cluster")
            plt.xlabel("Engineered feature")
            plt.ylabel("Cluster")
            plt.tight_layout()
            plt.show()
            """
        ),
        md(
            """
            The cluster heatmap confirms that each segment is driven by a different mix of volume, coverage, and party concentration. This is the core reason the clustering output is useful: it reduces many party-level columns into a smaller number of operational segments.
            """
        ),
        md("## 11. Strategy Brief for Each Segment / Cluster"),
        code(
            """
            cluster_profiles_export = cluster_profiles_df.merge(
                clustered_df.groupby("cluster_id")["lga_name"].apply(lambda values: ", ".join(sorted(values))).rename("lga_members"),
                on="cluster_id",
                how="left",
            )
            display(cluster_profiles_export.round(4))
            """
        ),
        code(
            """
            cluster_profiles_export.to_csv("analysis_outputs/cluster_profiles.csv", index=False)
            clustered_df.to_csv("analysis_outputs/cluster_assignments.csv", index=False)
            print("Saved analysis_outputs/cluster_profiles.csv")
            print("Saved analysis_outputs/cluster_assignments.csv")
            """
        ),
        md(
            """
            **Cluster 0:** lower-volume focused LGAs.  
            These LGAs should receive targeted ward-level mobilization, low-cost field operations, and sharper local messaging because the total vote base is smaller and gains can come from disciplined execution.

            **Cluster 1:** high-volume competitive LGAs.  
            These LGAs deserve the strongest election-day operations, turnout protection, agent coverage, and rapid incident monitoring because they combine scale with meaningful competition.

            **Cluster 2:** distinct high-coverage smaller LGAs.  
            These LGAs are analytically valuable because coverage is high and behavior is clear. They can be used as signal-rich benchmarks for monitoring how party structure differs from the broader field.
            """
        ),
        md(
            """
            ## 12. Final Conclusion and Limitations

            This analysis shows that the Delta State election sample is better understood as two related problems. The first problem is **coverage and completeness** across all 25 LGAs: most LGAs have usable polling-unit metadata but no announced polling-unit result rows. The second problem is **behavioral segmentation** across the 8 result-backed LGAs: once we restrict the data to LGAs with real vote information, meaningful differences appear in total vote scale, party concentration, and competitiveness.

            The final model uses hierarchical clustering with three segments because it matches the small-sample context, aligns with internal clustering metrics, and produces interpretable strategy groupings. The most important operational insight is that high-volume LGAs should not all be treated the same way. Some are more competitive and need persuasion and protection, while others look more like strongholds that need margin defense and turnout efficiency. Lower-volume LGAs need sharper local execution rather than blanket resource allocation.

            The biggest limitation is the size and completeness of the announced-result sample. Only 8 LGAs are cluster-eligible, so the output should be treated as a planning aid instead of a definitive statewide forecast. If more polling-unit results become available, the same feature engineering and clustering workflow can be rerun to produce a stronger segmentation analysis.
            """
        ),
    ]

    nb["cells"] = cells
    return nb


def main():
    notebook = build_notebook()
    output_path = ROOT_DIR / "ML_Submission_Template.ipynb"
    output_path.write_text(nbf.writes(notebook))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
