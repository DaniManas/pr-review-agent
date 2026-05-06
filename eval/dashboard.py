import glob
import json
import os

import pandas as pd
import streamlit as st

RESULTS_DIR = "eval/results"


def _run_id_from_path(path: str) -> str:
    filename = os.path.basename(path)
    return filename.removesuffix("_results.json")


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


def view_overview(df: pd.DataFrame):
    st.header("Overview Scores")
    if df.empty:
        st.warning("No results found in eval/results/. Run eval/runner.py first.")
        return
    col1, col2, col3 = st.columns(3)
    col1.metric("Avg Recall", f"{df['recall'].mean():.2%}")
    col2.metric("Avg Precision", f"{df['precision'].mean():.2%}")
    col3.metric("Total PRs Evaluated", len(df))
    st.subheader("All runs")
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
        st.markdown(f"[View LangSmith trace](https://smith.langchain.com/public/{row['langsmith_trace_id']}/r)")
    else:
        st.write("No LangSmith trace ID recorded.")


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
    st.bar_chart(grouped.set_index("prompt_version")[["avg_recall", "avg_precision"]])


def view_cost_latency(df: pd.DataFrame):
    st.header("Cost & Latency Trends")
    if df.empty:
        st.warning("No results found.")
        return
    df_sorted = df.sort_values("run_at")
    st.subheader("Latency over time")
    st.line_chart(df_sorted.set_index("run_at")[["latency_ms"]])
    st.subheader("Cost over time")
    st.line_chart(df_sorted.set_index("run_at")[["cost_usd"]])
    st.subheader("Cost by prompt version")
    st.bar_chart(df.groupby("prompt_version")["cost_usd"].mean())


def main():
    st.set_page_config(page_title="PR Review Agent — Eval Dashboard", layout="wide")
    st.title("PR Review Agent — Evaluation Dashboard")
    all_results = load_all_results()
    scope = st.sidebar.selectbox(
        "Result Scope",
        ["Latest run", "Latest per PR", "All historical runs"],
    )
    if scope == "Latest run":
        df = filter_latest_run(all_results)
    elif scope == "Latest per PR":
        df = filter_latest_per_pr(all_results)
    else:
        df = all_results

    if not all_results.empty:
        st.sidebar.caption(f"Loaded {len(all_results)} result rows from {all_results['result_file'].nunique()} files.")
    view = st.sidebar.radio(
        "View",
        ["Overview Scores", "Per-Run Detail", "Prompt Version Comparison", "Cost & Latency Trends"],
    )
    if view == "Overview Scores":
        view_overview(df)
    elif view == "Per-Run Detail":
        view_per_run(df)
    elif view == "Prompt Version Comparison":
        view_prompt_comparison(df)
    elif view == "Cost & Latency Trends":
        view_cost_latency(df)


if __name__ == "__main__":
    main()
