import glob
import json
import os

import altair as alt
import httpx
import pandas as pd
import streamlit as st

RESULTS_DIR = "eval/results"
LIVE_RUN_COLUMNS = [
    "id",
    "pr_number",
    "repo",
    "prompt_version",
    "overall_risk",
    "comment_count",
    "latency_ms",
    "cost_usd",
    "status",
    "error_message",
    "langsmith_trace_id",
    "created_at",
]


def _run_id_from_path(path: str) -> str:
    filename = os.path.basename(path)
    return filename.removesuffix("_results.json")


def env_value(name: str, env_path: str = ".env") -> str:
    value = os.getenv(name)
    if value:
        return value
    if not os.path.exists(env_path):
        return ""
    with open(env_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, env_value_raw = line.split("=", 1)
            if key.strip() == name:
                return env_value_raw.strip().strip("\"'")
    return ""


def format_cost(cost_usd) -> str:
    if cost_usd is None or pd.isna(cost_usd):
        return "N/A"
    return f"${cost_usd:.4f}"


def load_all_results(results_dir: str = RESULTS_DIR) -> pd.DataFrame:
    rows = []
    for path in glob.glob(os.path.join(results_dir, "*.json")):
        result_file = os.path.basename(path)
        run_id = _run_id_from_path(path)
        with open(path) as f:
            results = json.load(f)
        for r in results:
            rows.append({
                "result_file": result_file,
                "run_id": run_id,
                "pr_id": r["pr_id"],
                "repo": r["repo"],
                "pr_number": r["pr_number"],
                "prompt_version": r["prompt_version"],
                "recall": r["score"]["recall"],
                "precision": r["score"]["precision"],
                "true_positives": len(r["score"]["true_positives"]),
                "false_positives": len(r["score"]["false_positives"]),
                "false_negatives": len(r["score"]["false_negatives"]),
                "true_positive_items": r["score"]["true_positives"],
                "false_positive_items": r["score"]["false_positives"],
                "false_negative_items": r["score"]["false_negatives"],
                "judge_reasoning": r["score"].get("reasoning", ""),
                "overall_risk": r["review"]["overall_risk"],
                "comment_count": len(r["review"]["comments"]),
                "latency_ms": r["review"]["latency_ms"],
                "cost_usd": r["review"]["cost_usd"],
                "langsmith_trace_id": r.get("langsmith_trace_id"),
                "run_at": r["run_at"],
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["run_at"] = pd.to_datetime(df["run_at"])
    return df


@st.cache_data(ttl=30)
def load_live_runs(limit: int = 100) -> pd.DataFrame:
    supabase_url = env_value("SUPABASE_URL").rstrip("/")
    service_key = env_value("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        return pd.DataFrame(columns=LIVE_RUN_COLUMNS)

    response = httpx.get(
        f"{supabase_url}/rest/v1/reviews",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
        },
        params={
            "select": ",".join(LIVE_RUN_COLUMNS),
            "order": "created_at.desc",
            "limit": str(limit),
        },
        timeout=10,
    )
    response.raise_for_status()
    df = pd.DataFrame(response.json(), columns=LIVE_RUN_COLUMNS)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def filter_latest_run(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    latest_run_id = df.sort_values("run_at")["run_id"].iloc[-1]
    return df[df["run_id"] == latest_run_id].copy()


def filter_latest_per_pr(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.sort_values("run_at")
        .drop_duplicates(subset=["pr_id"], keep="last")
        .sort_values(["pr_number", "run_at"])
        .copy()
    )


def weakest_prs(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    if df.empty:
        return df
    columns = ["pr_id", "pr_number", "recall", "precision", "comment_count"]
    available_columns = [column for column in columns if column in df.columns]
    return df.sort_values(["recall", "precision"], ascending=[True, True])[available_columns].head(limit)


def get_issue_lists_for_row(row) -> dict[str, list[str]]:
    return {
        "true_positives": list(row.get("true_positive_items") or []),
        "false_positives": list(row.get("false_positive_items") or []),
        "false_negatives": list(row.get("false_negative_items") or []),
    }


def issue_list_frame(items: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"issue": items}) if items else pd.DataFrame({"issue": ["None"]})


def prompt_metric_chart_data(grouped: pd.DataFrame) -> pd.DataFrame:
    return grouped.melt(
        id_vars=["prompt_version"],
        value_vars=["avg_recall", "avg_precision"],
        var_name="metric",
        value_name="score",
    ).replace({
        "metric": {
            "avg_recall": "Recall",
            "avg_precision": "Precision",
        }
    })


def has_cost_data(df: pd.DataFrame) -> bool:
    return "cost_usd" in df.columns and df["cost_usd"].notna().any()


def cost_latency_summary(df: pd.DataFrame) -> dict[str, float | None]:
    avg_latency_ms = float(df["latency_ms"].mean()) if "latency_ms" in df.columns and not df.empty else None
    avg_cost_usd = float(df["cost_usd"].mean()) if has_cost_data(df) else None
    return {
        "avg_latency_ms": avg_latency_ms,
        "avg_latency_seconds": None if avg_latency_ms is None else avg_latency_ms / 1000,
        "avg_cost_usd": avg_cost_usd,
    }


def live_run_summary(df: pd.DataFrame) -> dict[str, float | int | None]:
    if df.empty:
        return {
            "total_runs": 0,
            "success_runs": 0,
            "failed_runs": 0,
            "avg_latency_seconds": None,
            "avg_cost_usd": None,
        }
    cost = pd.to_numeric(df["cost_usd"], errors="coerce") if "cost_usd" in df.columns else pd.Series(dtype=float)
    latency = pd.to_numeric(df["latency_ms"], errors="coerce") if "latency_ms" in df.columns else pd.Series(dtype=float)
    return {
        "total_runs": int(len(df)),
        "success_runs": int((df["status"] == "success").sum()),
        "failed_runs": int((df["status"] == "failed").sum()),
        "avg_latency_seconds": None if latency.dropna().empty else float(latency.mean() / 1000),
        "avg_cost_usd": None if cost.dropna().empty else float(cost.mean()),
    }


def view_overview(df: pd.DataFrame):
    st.header("Overview Scores")
    if df.empty:
        st.warning("No results found in eval/results/. Run eval/runner.py first.")
        return
    run_label = "Multiple runs"
    if df["run_id"].nunique() == 1:
        run_label = df["run_id"].iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Avg Recall", f"{df['recall'].mean():.2%}")
    col2.metric("Avg Precision", f"{df['precision'].mean():.2%}")
    col3.metric("Total PRs Evaluated", len(df))
    col4.metric("Run", run_label)

    st.subheader("Confusion Breakdown")
    breakdown = pd.DataFrame([{
        "true_positives": int(df["true_positives"].sum()),
        "false_positives": int(df["false_positives"].sum()),
        "false_negatives": int(df["false_negatives"].sum()),
    }])
    st.dataframe(breakdown, hide_index=True)

    st.subheader("Weakest PRs")
    st.dataframe(weakest_prs(df), hide_index=True)

    st.subheader("Runs")
    st.dataframe(
        df[[
            "pr_id",
            "run_id",
            "prompt_version",
            "recall",
            "precision",
            "overall_risk",
            "comment_count",
            "run_at",
        ]]
    )


def view_per_run(df: pd.DataFrame):
    st.header("Per-Run Detail")
    if df.empty:
        st.warning("No results found.")
        return
    options = {
        f"{row.pr_id} | {row.run_id}": index
        for index, row in df.sort_values(["pr_number", "run_at"]).iterrows()
    }
    selected = st.selectbox("Select PR", list(options.keys()))
    row = df.loc[options[selected]]
    st.subheader(f"PR: {selected}")
    st.write(f"**Repo:** {row['repo']} | **PR #:** {row['pr_number']}")
    st.write(f"**Prompt version:** {row['prompt_version']}")
    st.write(f"**Overall risk:** {row['overall_risk']}")
    st.write(
        f"**Comments:** {row['comment_count']} | "
        f"**Latency:** {row['latency_ms']} ms | "
        f"**Cost:** {format_cost(row['cost_usd'])}"
    )
    col1, col2 = st.columns(2)
    col1.metric("Recall", f"{row['recall']:.2%}")
    col2.metric("Precision", f"{row['precision']:.2%}")
    if row["langsmith_trace_id"]:
        st.write("**LangSmith trace ID:**")
        st.code(row["langsmith_trace_id"], language=None)
        st.caption(
            "Open the private LangSmith project and search for this run ID. "
            "A direct public trace link only works after the trace is explicitly shared in LangSmith."
        )
    else:
        st.write("No LangSmith trace ID recorded.")

    issues = get_issue_lists_for_row(row)
    with st.expander(f"True positives ({len(issues['true_positives'])})", expanded=True):
        st.dataframe(issue_list_frame(issues["true_positives"]), hide_index=True)
    with st.expander(f"False positives ({len(issues['false_positives'])})", expanded=True):
        st.dataframe(issue_list_frame(issues["false_positives"]), hide_index=True)
    with st.expander(f"False negatives ({len(issues['false_negatives'])})", expanded=True):
        st.dataframe(issue_list_frame(issues["false_negatives"]), hide_index=True)

    if row.get("judge_reasoning"):
        with st.expander("Judge reasoning"):
            st.write(row["judge_reasoning"])


def view_prompt_comparison(df: pd.DataFrame):
    st.header("Prompt Version Comparison")
    if df.empty:
        st.warning("No results found.")
        return
    grouped = df.groupby("prompt_version").agg(
        avg_recall=("recall", "mean"),
        avg_precision=("precision", "mean"),
        avg_latency_ms=("latency_ms", "mean"),
        avg_cost_usd=("cost_usd", "mean"),
        count=("pr_id", "count"),
    ).reset_index()
    st.dataframe(grouped)
    chart_data = prompt_metric_chart_data(grouped)
    chart = (
        alt.Chart(chart_data)
        .mark_bar()
        .encode(
            x=alt.X("prompt_version:N", title="Prompt Version"),
            xOffset=alt.XOffset("metric:N"),
            y=alt.Y("score:Q", title="Score", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("metric:N", title="Metric"),
            tooltip=[
                alt.Tooltip("prompt_version:N", title="Prompt"),
                alt.Tooltip("metric:N", title="Metric"),
                alt.Tooltip("score:Q", title="Score", format=".2%"),
            ],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def view_cost_latency(df: pd.DataFrame):
    st.header("Cost & Latency Trends")
    if df.empty:
        st.warning("No results found.")
        return
    df_sorted = df.sort_values("run_at")
    summary = cost_latency_summary(df)
    col1, col2 = st.columns(2)
    col1.metric("Avg Latency", f"{summary['avg_latency_seconds']:.2f}s")
    col2.metric(
        "Avg Cost",
        "N/A" if summary["avg_cost_usd"] is None else f"${summary['avg_cost_usd']:.4f}",
    )

    st.subheader("Latency over time")
    st.line_chart(df_sorted.set_index("run_at")[["latency_ms"]])

    if not has_cost_data(df):
        st.subheader("Cost")
        st.info("Cost tracking is not available yet. `cost_usd` is currently N/A for all runs.")
        return

    st.subheader("Cost over time")
    st.line_chart(df_sorted.set_index("run_at")[["cost_usd"]])
    st.subheader("Cost by prompt version")
    st.bar_chart(df.groupby("prompt_version")["cost_usd"].mean())


def view_live_runs(df: pd.DataFrame):
    st.header("Live Runs")
    st.caption("Production webhook runs stored in Supabase. These are operational logs, not ground-truth eval scores.")
    if df.empty:
        st.warning("No live runs found. Confirm SUPABASE_URL and SUPABASE_SERVICE_KEY are set and the Supabase project is active.")
        return

    summary = live_run_summary(df)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Runs", summary["total_runs"])
    col2.metric("Successful", summary["success_runs"])
    col3.metric("Failed", summary["failed_runs"])
    col4.metric(
        "Avg Latency",
        "N/A" if summary["avg_latency_seconds"] is None else f"{summary['avg_latency_seconds']:.2f}s",
    )
    col5.metric(
        "Avg Cost",
        "N/A" if summary["avg_cost_usd"] is None else f"${summary['avg_cost_usd']:.4f}",
    )

    st.subheader("Recent Runs")
    display_columns = [
        "created_at",
        "pr_number",
        "repo",
        "status",
        "overall_risk",
        "comment_count",
        "latency_ms",
        "cost_usd",
        "prompt_version",
        "langsmith_trace_id",
        "error_message",
    ]
    st.dataframe(df[display_columns], hide_index=True, use_container_width=True)

    trend_df = df.dropna(subset=["created_at"]).sort_values("created_at")
    if not trend_df.empty:
        st.subheader("Latency over time")
        st.line_chart(trend_df.set_index("created_at")[["latency_ms"]])

    if has_cost_data(df):
        st.subheader("Cost over time")
        st.line_chart(trend_df.set_index("created_at")[["cost_usd"]])


def main():
    st.set_page_config(page_title="PR Review Agent — Eval Dashboard", layout="wide")
    st.title("PR Review Agent — Evaluation Dashboard")
    all_results = load_all_results()
    live_runs = load_live_runs()
    scope = st.sidebar.selectbox(
        "Result Scope",
        ["Latest run", "Latest per PR", "All historical runs"],
        index=1,
        help=(
            "Latest per PR keeps one current row for each evaluated PR. "
            "Latest run shows only the newest result file."
        ),
    )
    if scope == "Latest run":
        df = filter_latest_run(all_results)
    elif scope == "Latest per PR":
        df = filter_latest_per_pr(all_results)
    else:
        df = all_results

    if not all_results.empty:
        st.sidebar.caption(f"Loaded {len(all_results)} result rows from {all_results['result_file'].nunique()} files.")
    if not live_runs.empty:
        st.sidebar.caption(f"Loaded {len(live_runs)} live Supabase runs.")
    view = st.sidebar.radio(
        "View",
        ["Overview Scores", "Per-Run Detail", "Prompt Version Comparison", "Cost & Latency Trends", "Live Runs"],
    )
    if view == "Overview Scores":
        view_overview(df)
    elif view == "Per-Run Detail":
        view_per_run(df)
    elif view == "Prompt Version Comparison":
        view_prompt_comparison(df)
    elif view == "Cost & Latency Trends":
        view_cost_latency(df)
    elif view == "Live Runs":
        view_live_runs(live_runs)


if __name__ == "__main__":
    main()
