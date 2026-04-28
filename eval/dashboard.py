import glob
import json
import os

import pandas as pd
import streamlit as st

RESULTS_DIR = "eval/results"


def format_cost(cost) -> str:
    if cost is None or pd.isna(cost):
        return "N/A"
    return f"${cost:.4f}"


def load_all_results() -> pd.DataFrame:
    rows = []
    for path in glob.glob(os.path.join(RESULTS_DIR, "*.json")):
        with open(path) as f:
            results = json.load(f)
        for r in results:
            rows.append({
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
    st.dataframe(df[["pr_id", "prompt_version", "recall", "precision", "overall_risk", "comment_count", "run_at"]])


def view_per_run(df: pd.DataFrame):
    st.header("Per-Run Detail")
    if df.empty:
        st.warning("No results found.")
        return
    pr_ids = df["pr_id"].tolist()
    selected = st.selectbox("Select PR", pr_ids)
    row = df[df["pr_id"] == selected].iloc[0]
    st.subheader(f"PR: {selected}")
    st.write(f"**Repo:** {row['repo']} | **PR #:** {row['pr_number']}")
    st.write(f"**Prompt version:** {row['prompt_version']}")
    st.write(f"**Overall risk:** {row['overall_risk']}")
    st.write(f"**Comments:** {row['comment_count']} | **Latency:** {row['latency_ms']} ms | **Cost:** {format_cost(row['cost_usd'])}")
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
        avg_cost_usd=("cost_usd", lambda s: s.dropna().mean() if not s.dropna().empty else None),
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
    cost_df = df_sorted.dropna(subset=["cost_usd"])
    if cost_df.empty:
        st.info("Cost data is unavailable until provider usage tracking is implemented.")
    else:
        st.line_chart(cost_df.set_index("run_at")[["cost_usd"]])
    st.subheader("Cost by prompt version")
    grouped_cost = cost_df.groupby("prompt_version")["cost_usd"].mean() if not cost_df.empty else None
    if grouped_cost is not None and not grouped_cost.empty:
        st.bar_chart(grouped_cost)


def main():
    st.set_page_config(page_title="PR Review Agent — Eval Dashboard", layout="wide")
    st.title("PR Review Agent — Evaluation Dashboard")
    df = load_all_results()
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
