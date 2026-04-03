#!/usr/bin/env python3
import os
import sqlite3
from pathlib import Path

if not os.environ.get("LOKY_MAX_CPU_COUNT"):
    os.environ["LOKY_MAX_CPU_COUNT"] = "4"

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.preprocessing import MinMaxScaler, StandardScaler

DELTA_STATE_ID = 25
RESULT_BACKED_LGA_IDS = [6, 7, 17, 19, 21, 22, 34, 35]
PARTY_ORDER = ["PDP", "DPP", "ACN", "PPA", "CDC", "JP", "ANPP", "LABO", "CPP"]
PARTY_ALIASES = {"LABOUR": "LABO"}


def get_connection(db_path: str | Path = "db.sqlite3") -> sqlite3.Connection:
    return sqlite3.connect(Path(db_path))


def normalize_party_code(code: str | None) -> str:
    normalized = (code or "").strip().upper()
    return PARTY_ALIASES.get(normalized, normalized)


def normalize_party_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().replace(PARTY_ALIASES)


def load_election_frames(db_path: str | Path = "db.sqlite3") -> dict[str, pd.DataFrame]:
    with get_connection(db_path) as connection:
        lga = pd.read_sql_query(
            "SELECT uniqueid, lga_id, lga_name, state_id FROM lga WHERE state_id = ? ORDER BY lga_name",
            connection,
            params=(DELTA_STATE_ID,),
        )
        ward = pd.read_sql_query(
            "SELECT uniqueid, ward_id, ward_name, lga_id FROM ward ORDER BY ward_name",
            connection,
        )
        polling_unit = pd.read_sql_query(
            """
            SELECT uniqueid, polling_unit_id, ward_id, lga_id, uniquewardid,
                   polling_unit_number, polling_unit_name, polling_unit_description
            FROM polling_unit
            """,
            connection,
        )
        pu_results = pd.read_sql_query(
            """
            SELECT result_id, polling_unit_uniqueid, party_abbreviation, party_score,
                   entered_by_user, date_entered
            FROM announced_pu_results
            """,
            connection,
        )
        lga_results = pd.read_sql_query(
            """
            SELECT result_id, lga_name, party_abbreviation, party_score
            FROM announced_lga_results
            """,
            connection,
        )

    pu_results["party_abbreviation"] = normalize_party_series(pu_results["party_abbreviation"])
    lga_results["party_abbreviation"] = normalize_party_series(lga_results["party_abbreviation"])
    pu_results["polling_unit_uniqueid"] = pu_results["polling_unit_uniqueid"].astype(int)
    lga_results["lga_name"] = lga_results["lga_name"].astype(str)

    return {
        "lga": lga,
        "ward": ward,
        "polling_unit": polling_unit,
        "announced_pu_results": pu_results,
        "announced_lga_results": lga_results,
    }


def get_usable_polling_units(polling_unit: pd.DataFrame) -> pd.DataFrame:
    return polling_unit.loc[
        polling_unit["polling_unit_number"].notna()
        & (polling_unit["polling_unit_number"] != "")
        & polling_unit["polling_unit_name"].notna()
        & (polling_unit["polling_unit_name"] != "")
        & (polling_unit["lga_id"] != 0)
        & (polling_unit["polling_unit_id"] != 0)
    ].copy()


def build_completeness_table(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lga = frames["lga"].copy()
    usable_polling_units = get_usable_polling_units(frames["polling_unit"])
    pu_results = frames["announced_pu_results"].copy()

    polling_units_with_results = (
        pu_results[["polling_unit_uniqueid"]]
        .drop_duplicates()
        .rename(columns={"polling_unit_uniqueid": "uniqueid"})
        .merge(usable_polling_units[["uniqueid", "lga_id"]], on="uniqueid", how="left")
        .dropna(subset=["lga_id"])
    )

    completeness = (
        lga[["lga_id", "lga_name"]]
        .merge(
            usable_polling_units.groupby("lga_id")["uniqueid"]
            .nunique()
            .rename("polling_units_with_metadata")
            .reset_index(),
            on="lga_id",
            how="left",
        )
        .merge(
            polling_units_with_results.groupby("lga_id")["uniqueid"]
            .nunique()
            .rename("polling_units_with_results")
            .reset_index(),
            on="lga_id",
            how="left",
        )
        .fillna({"polling_units_with_metadata": 0, "polling_units_with_results": 0})
    )

    completeness["polling_units_with_metadata"] = completeness["polling_units_with_metadata"].astype(int)
    completeness["polling_units_with_results"] = completeness["polling_units_with_results"].astype(int)
    completeness["coverage_pct"] = np.where(
        completeness["polling_units_with_metadata"] > 0,
        (completeness["polling_units_with_results"] / completeness["polling_units_with_metadata"]) * 100,
        0.0,
    )
    completeness["result_status"] = np.where(
        completeness["polling_units_with_results"] > 0,
        "announced polling-unit results available",
        "no announced polling-unit results available",
    )
    return completeness.sort_values("lga_name").reset_index(drop=True)


def build_lga_result_long(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    usable_polling_units = get_usable_polling_units(frames["polling_unit"])
    lga = frames["lga"][["lga_id", "lga_name"]]
    pu_results = frames["announced_pu_results"]

    result_long = (
        pu_results.merge(
            usable_polling_units[["uniqueid", "lga_id"]],
            left_on="polling_unit_uniqueid",
            right_on="uniqueid",
            how="inner",
        )
        .merge(lga, on="lga_id", how="left")
        .drop(columns=["uniqueid"])
    )
    return result_long.sort_values(["lga_name", "party_abbreviation"]).reset_index(drop=True)


def build_lga_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    result_long = build_lga_result_long(frames)
    summary = (
        result_long.groupby(["lga_id", "lga_name", "party_abbreviation"], as_index=False)
        .agg(total_score=("party_score", "sum"), row_count=("party_score", "size"))
        .sort_values(["lga_name", "total_score"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return summary


def build_party_share_table(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    summary = build_lga_summary(frames)
    party_share = (
        summary.groupby("party_abbreviation", as_index=False)["total_score"]
        .sum()
        .sort_values("total_score", ascending=False)
        .reset_index(drop=True)
    )
    total_votes = party_share["total_score"].sum()
    party_share["vote_share_pct"] = (party_share["total_score"] / total_votes * 100).round(2)
    return party_share


def build_modeling_dataset(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    completeness = build_completeness_table(frames)
    summary = build_lga_summary(frames)

    pivot = (
        summary.pivot_table(
            index=["lga_id", "lga_name"],
            columns="party_abbreviation",
            values="total_score",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(columns=PARTY_ORDER, fill_value=0)
        .reset_index()
    )

    vote_columns = PARTY_ORDER.copy()
    pivot["total_votes"] = pivot[vote_columns].sum(axis=1)

    for party in PARTY_ORDER:
        pivot[f"share_{party.lower()}"] = np.where(
            pivot["total_votes"] > 0,
            pivot[party] / pivot["total_votes"],
            0.0,
        )

    share_columns = [f"share_{party.lower()}" for party in PARTY_ORDER]
    pivot["dominant_party"] = pivot[share_columns].idxmax(axis=1).str.replace("share_", "", regex=False).str.upper()
    pivot["dominant_party_share"] = pivot[share_columns].max(axis=1)

    share_matrix = np.sort(pivot[share_columns].to_numpy(), axis=1)
    pivot["second_party_share"] = share_matrix[:, -2]
    pivot["competitiveness_margin"] = pivot["dominant_party_share"] - pivot["second_party_share"]
    pivot["vote_dispersion"] = pivot[share_columns].std(axis=1)
    pivot["effective_party_count"] = np.where(
        (pivot[share_columns] ** 2).sum(axis=1) > 0,
        1 / (pivot[share_columns] ** 2).sum(axis=1),
        0.0,
    )

    modeling = (
        completeness.merge(pivot, on=["lga_id", "lga_name"], how="left")
        .sort_values("lga_name")
        .reset_index(drop=True)
    )

    result_backed = modeling.loc[modeling["polling_units_with_results"] > 0].copy()
    result_backed["is_result_backed"] = True
    result_backed["coverage_pct"] = result_backed["coverage_pct"].round(2)
    return result_backed


def get_feature_columns(modeling_df: pd.DataFrame) -> list[str]:
    share_columns = [f"share_{party.lower()}" for party in PARTY_ORDER]
    return [
        "polling_units_with_results",
        "polling_units_with_metadata",
        "coverage_pct",
        "total_votes",
        *share_columns,
        "dominant_party_share",
        "competitiveness_margin",
        "vote_dispersion",
        "effective_party_count",
    ]


def scale_features(modeling_df: pd.DataFrame, feature_columns: list[str]) -> dict[str, pd.DataFrame]:
    raw = modeling_df[feature_columns].copy()
    standard_scaler = StandardScaler()
    minmax_scaler = MinMaxScaler()

    standard_df = pd.DataFrame(
        standard_scaler.fit_transform(raw),
        columns=feature_columns,
        index=modeling_df["lga_name"],
    )
    minmax_df = pd.DataFrame(
        minmax_scaler.fit_transform(raw),
        columns=feature_columns,
        index=modeling_df["lga_name"],
    )

    return {"raw": raw.set_index(modeling_df["lga_name"]), "standard": standard_df, "minmax": minmax_df}


def evaluate_clustering_options(modeling_df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    scaled = scale_features(modeling_df, feature_columns)["standard"]
    X = scaled.to_numpy()
    rows = []
    for k in range(2, 5):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=20)
        kmeans_labels = kmeans.fit_predict(X)
        rows.append(
            {
                "method": "kmeans",
                "k": k,
                "silhouette_score": silhouette_score(X, kmeans_labels),
                "calinski_harabasz_score": calinski_harabasz_score(X, kmeans_labels),
                "davies_bouldin_score": davies_bouldin_score(X, kmeans_labels),
                "inertia": kmeans.inertia_,
            }
        )

        hierarchical = AgglomerativeClustering(n_clusters=k, linkage="ward")
        hierarchical_labels = hierarchical.fit_predict(X)
        rows.append(
            {
                "method": "hierarchical_ward",
                "k": k,
                "silhouette_score": silhouette_score(X, hierarchical_labels),
                "calinski_harabasz_score": calinski_harabasz_score(X, hierarchical_labels),
                "davies_bouldin_score": davies_bouldin_score(X, hierarchical_labels),
                "inertia": np.nan,
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["method", "silhouette_score", "calinski_harabasz_score"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def choose_final_clustering(evaluation_df: pd.DataFrame) -> tuple[str, int]:
    hierarchical_best = (
        evaluation_df.loc[evaluation_df["method"] == "hierarchical_ward"]
        .sort_values(["silhouette_score", "calinski_harabasz_score"], ascending=[False, False])
        .iloc[0]
    )
    kmeans_best = (
        evaluation_df.loc[evaluation_df["method"] == "kmeans"]
        .sort_values(["silhouette_score", "calinski_harabasz_score"], ascending=[False, False])
        .iloc[0]
    )

    if (
        kmeans_best["silhouette_score"] > hierarchical_best["silhouette_score"] + 0.05
        and kmeans_best["davies_bouldin_score"] < hierarchical_best["davies_bouldin_score"]
    ):
        return "kmeans", int(kmeans_best["k"])
    return "hierarchical_ward", int(hierarchical_best["k"])


def fit_final_clustering(modeling_df: pd.DataFrame, feature_columns: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    scaled = scale_features(modeling_df, feature_columns)["standard"]
    evaluation = evaluate_clustering_options(modeling_df, feature_columns)
    method, k = choose_final_clustering(evaluation)
    X = scaled.to_numpy()

    if method == "kmeans":
        model = KMeans(n_clusters=k, random_state=42, n_init=20)
    else:
        model = AgglomerativeClustering(n_clusters=k, linkage="ward")

    labels = model.fit_predict(X)
    clustered = modeling_df.copy()
    clustered["cluster_id"] = labels
    clustered["cluster_id"] = clustered["cluster_id"].astype(int)

    pca = PCA(n_components=2, random_state=42)
    pca_points = pca.fit_transform(X)
    clustered["pca_1"] = pca_points[:, 0]
    clustered["pca_2"] = pca_points[:, 1]
    clustered["final_method"] = method
    clustered["final_k"] = k
    return clustered, evaluation


def build_cluster_profiles(clustered_df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    profile = (
        clustered_df.groupby("cluster_id", as_index=False)[
            ["total_votes", "coverage_pct", "dominant_party_share", "competitiveness_margin", "vote_dispersion"]
        ]
        .mean()
    )

    total_votes_median = clustered_df["total_votes"].median()
    competitiveness_median = clustered_df["competitiveness_margin"].median()

    labels = []
    strategies = []
    for _, row in profile.iterrows():
        if row["total_votes"] >= total_votes_median and row["competitiveness_margin"] <= competitiveness_median:
            label = "high-volume competitive LGAs"
            strategy = "Prioritize coalition building, turnout protection, and rapid result monitoring because these LGAs are large and closely contested."
        elif row["total_votes"] >= total_votes_median:
            label = "high-volume dominant-party LGAs"
            strategy = "Protect strongholds, focus on turnout efficiency, and defend vote margins with strong polling-unit operations."
        else:
            label = "lower-volume focused LGAs"
            strategy = "Use targeted local messaging, ward-level mobilization, and cost-efficient field operations because scale is smaller."
        labels.append(label)
        strategies.append(strategy)

    profile["cluster_label"] = labels
    profile["strategy_brief"] = strategies
    return profile


def build_dendrogram_linkage(modeling_df: pd.DataFrame, feature_columns: list[str]) -> np.ndarray:
    scaled = scale_features(modeling_df, feature_columns)["standard"]
    return linkage(scaled.to_numpy(), method="ward")


def export_ml_artifacts(db_path: str | Path = "db.sqlite3", out_dir: str | Path = "analysis_outputs") -> dict[str, Path]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    frames = load_election_frames(db_path)
    completeness = build_completeness_table(frames)
    lga_summary = build_lga_summary(frames)
    party_share = build_party_share_table(frames)
    modeling_dataset = build_modeling_dataset(frames)

    outputs = {
        "polling_unit_completeness": out_path / "polling_unit_completeness.csv",
        "lga_summary": out_path / "lga_summary.csv",
        "party_share": out_path / "party_share.csv",
        "lga_modeling_dataset": out_path / "lga_modeling_dataset.csv",
    }

    completeness.to_csv(outputs["polling_unit_completeness"], index=False)
    lga_summary.to_csv(outputs["lga_summary"], index=False)
    party_share.to_csv(outputs["party_share"], index=False)
    modeling_dataset.to_csv(outputs["lga_modeling_dataset"], index=False)
    return outputs
