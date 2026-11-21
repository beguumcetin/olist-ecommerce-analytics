"""Headline numbers, the delivery-delay regression, CSV exports and README figures.

    python -m src.analyze
"""

import json
import sys
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "olist.duckdb"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
TABLES = REPORTS / "tables"

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.dpi": 130, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlecolor": INK, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def headline(con) -> dict:
    q = lambda s: con.execute(s).fetchone()[0]
    return {
        "orders": q("SELECT COUNT(*) FROM fct_orders"),
        "customers": q("SELECT COUNT(DISTINCT customer_unique_id) FROM fct_orders"),
        "period": [str(q("SELECT MIN(purchase_month) FROM fct_orders")), str(q("SELECT MAX(purchase_month) FROM fct_orders"))],
        "repeat_customer_share": q("SELECT AVG((frequency >= 2)::INT) FROM mart_rfm"),
        "late_share_delivered": q("SELECT AVG(is_late::INT) FROM fct_orders WHERE order_status = 'delivered'"),
        "avg_score_on_time": q("SELECT AVG(review_score) FROM fct_orders WHERE order_status='delivered' AND NOT is_late"),
        "avg_score_late": q("SELECT AVG(review_score) FROM fct_orders WHERE order_status='delivered' AND is_late"),
        # Weighted by cohort size; a plain average of rates is dominated by the tiny 2016 cohorts.
        "month1_repeat_rate": q("""
            WITH c AS (
                SELECT cohort_month,
                       MAX(customers) FILTER (WHERE month_offset = 0) AS n0,
                       COALESCE(MAX(customers) FILTER (WHERE month_offset = 1), 0) AS n1
                FROM mart_cohorts GROUP BY 1 HAVING n0 >= 500
            ) SELECT SUM(n1)::DOUBLE / SUM(n0) FROM c
        """),
        "multi_seller_share": q("SELECT AVG((n_sellers > 1)::INT) FROM fct_orders WHERE order_status='delivered' AND review_score IS NOT NULL"),
        "score_multi_seller": q("SELECT AVG(review_score) FROM fct_orders WHERE order_status='delivered' AND n_sellers > 1"),
        "score_single_seller": q("SELECT AVG(review_score) FROM fct_orders WHERE order_status='delivered' AND n_sellers = 1"),
        "late_share_multi_seller": q("SELECT AVG(is_late::INT) FROM fct_orders WHERE order_status='delivered' AND n_sellers > 1"),
        "repeat_customers_revenue_share": q("SELECT SUM(monetary) FILTER (WHERE frequency >= 2) / SUM(monetary) FROM mart_rfm"),
    }


def delay_regression(con) -> dict:
    """Does a late delivery lower the review score once we hold the rest fixed?

    Observational, so this is an association with controls, not an experiment.
    Controls: what was bought, where it went, how big and how far the order was.
    """
    df = con.execute("""
        SELECT review_score, is_late::INT AS late, delivery_days, freight_share,
               n_items, (n_sellers > 1)::INT AS multi_seller, same_state::INT AS same_state,
               main_category, customer_state, installments
        FROM fct_orders
        WHERE order_status = 'delivered' AND review_score IS NOT NULL AND delivery_days IS NOT NULL
    """).df().dropna()
    top = df["main_category"].value_counts().index[:20]
    df["category"] = df["main_category"].where(df["main_category"].isin(top), "other")
    df["low_score"] = (df["review_score"] <= 2).astype(int)

    rhs = "late + delivery_days + freight_share + n_items + multi_seller + same_state + installments + C(category) + C(customer_state)"
    ols = smf.ols(f"review_score ~ {rhs}", df).fit(cov_type="HC1")
    logit = smf.logit(f"low_score ~ {rhs}", df).fit(disp=False)
    keep = ["late", "delivery_days", "freight_share", "n_items", "multi_seller", "same_state", "installments"]
    return {
        "n": int(len(df)),
        "ols_review_score": {k: {"coef": float(ols.params[k]), "ci95": [float(x) for x in ols.conf_int().loc[k]]} for k in keep},
        "logit_low_score_odds_ratio": {k: float(np.exp(logit.params[k])) for k in keep},
        "r2": float(ols.rsquared),
    }


def export_tables(con):
    TABLES.mkdir(parents=True, exist_ok=True)
    for t in ["mart_monthly", "mart_cohorts", "mart_rfm", "mart_delivery_reviews", "mart_states", "mart_categories"]:
        con.execute(f"SELECT * FROM {t}").df().to_csv(TABLES / f"{t}.csv", index=False)


def fig_monthly(con):
    m = con.execute("SELECT * FROM mart_monthly WHERE purchase_month BETWEEN '2017-01-01' AND '2018-08-01'").df()
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.bar(m.purchase_month, m.orders, width=20, color=BLUE)
    ax.set_title("Orders per month")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    save(fig, "monthly_orders.png")


def fig_cohorts(con, max_offset=12, min_size=500):
    c = con.execute("SELECT * FROM mart_cohorts").df()
    sizes = c[c.month_offset == 0].set_index("cohort_month")["customers"]
    keep = sizes[sizes >= min_size].index
    grid = (c[c.cohort_month.isin(keep) & c.month_offset.between(1, max_offset)]
            .pivot(index="cohort_month", columns="month_offset", values="retention") * 100)
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(grid) + 1.2))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)
    im = ax.imshow(grid.values, aspect="auto", cmap=cmap, vmin=0)
    ax.set_xticks(range(grid.shape[1]), grid.columns)
    ax.set_yticks(range(len(grid)), [pd.Timestamp(d).strftime("%Y-%m") for d in grid.index])
    ax.set_xlabel("Months after first purchase")
    ax.set_title("Share of each monthly cohort that bought again (%)")
    fig.colorbar(im, ax=ax, fraction=0.03, label="%")
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "cohort_retention.png")


def fig_delivery(con):
    d = con.execute("SELECT * FROM mart_delivery_reviews").df()
    labels = d.delivery_bucket.str[3:]
    colors = [BLUE if "late" not in l else ORANGE for l in labels]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    bars = ax.bar(labels, d.avg_score, color=colors, width=0.6)
    ax.bar_label(bars, labels=[f"{v:.2f}" for v in d.avg_score], padding=3, color=INK_2)
    ax.set_ylim(1, 5.2)
    ax.set_ylabel("Average review score (1-5)")
    ax.set_title("Review score by how the delivery compared with the promised date")
    ax.tick_params(axis="x", labelrotation=15)
    save(fig, "delivery_vs_review.png")


def fig_segments(con):
    s = con.execute("""
        SELECT segment, COUNT(*) AS customers, SUM(monetary) AS revenue
        FROM mart_rfm GROUP BY 1 ORDER BY revenue DESC
    """).df()
    s["customer_pct"] = s.customers / s.customers.sum() * 100
    s["revenue_pct"] = s.revenue / s.revenue.sum() * 100
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
    for ax, col, title in [(axes[0], "customer_pct", "Share of customers (%)"), (axes[1], "revenue_pct", "Share of revenue (%)")]:
        bars = ax.barh(s.segment[::-1], s[col][::-1], color=BLUE, height=0.6)
        ax.bar_label(bars, labels=[f"{v:.1f}" for v in s[col][::-1]], padding=3, color=INK_2)
        ax.set_title(title)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
    save(fig, "rfm_segments.png")


def fig_drivers(findings):
    """What moves the review score, holding the other factors fixed (OLS, 95% CI)."""
    ols = findings["delay_regression"]["ols_review_score"]
    rows = [("Delivered late", "late"), ("Items from 2+ sellers", "multi_seller"),
            ("Each extra item in the order", "n_items"), ("Each extra day of delivery time", "delivery_days")]
    fig, ax = plt.subplots(figsize=(8, 2.8))
    for i, (label, key) in enumerate(rows[::-1]):
        c, (lo, hi) = ols[key]["coef"], ols[key]["ci95"]
        ax.plot([lo, hi], [i, i], color=BLUE, lw=2)
        ax.plot(c, i, "o", color=BLUE, ms=8, mec="white", mew=2)
        ax.text(c, i + 0.28, f"{c:+.2f}", ha="center", color=INK_2, fontsize=9)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_ylim(-0.5, len(rows) - 0.1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows[::-1]])
    ax.set_xlabel("Change in review score (points, 1-5 scale)")
    ax.set_title("What lowers the review score, other factors held fixed")
    save(fig, "review_drivers.png")


def main(db_path: Path = DB_PATH):
    con = duckdb.connect(str(db_path), read_only=True)
    findings = {"headline": headline(con), "delay_regression": delay_regression(con)}
    export_tables(con)
    fig_monthly(con)
    fig_cohorts(con)
    fig_delivery(con)
    fig_segments(con)
    fig_drivers(findings)
    con.close()
    (REPORTS / "findings.json").write_text(json.dumps(findings, indent=2, default=str))
    print(json.dumps(findings["headline"], indent=2, default=str))
    print("late coef (review points):", round(findings["delay_regression"]["ols_review_score"]["late"]["coef"], 3))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH)
