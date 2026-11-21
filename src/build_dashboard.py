"""Bake the analysis results into one self-contained dashboard page.

Reads the DuckDB tables and reports/findings.json, fills dashboard/template.html
and writes docs/index.html (GitHub Pages can serve it from /docs).

    python -m src.build_dashboard
"""

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "olist.duckdb"
TEMPLATE = ROOT / "dashboard" / "template.html"
OUT = ROOT / "docs" / "index.html"

STATE_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará",
    "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins",
}
BUCKET_LABELS = {
    "1": "10+ days early", "2": "1-9 days early", "3": "On the day",
    "4": "1-3 days late", "5": "4-7 days late", "6": "8+ days late",
}


def build_data(con) -> dict:
    rows = lambda sql: con.execute(sql).fetchall()
    findings = json.loads((ROOT / "reports" / "findings.json").read_text())

    monthly = [
        {"month": str(m)[:7], "orders": o, "late": l, "score": s}
        for m, o, l, s in rows("""
            SELECT purchase_month, orders, late_share, avg_score FROM mart_monthly
            WHERE purchase_month BETWEEN '2017-01-01' AND '2018-08-01' ORDER BY 1""")
    ]
    delivery = [
        {"label": BUCKET_LABELS[b[0]], "late": "late" in b, "orders": o, "score": s, "low": low}
        for b, o, s, low in rows("SELECT delivery_bucket, orders, avg_score, low_score_share FROM mart_delivery_reviews ORDER BY 1")
    ]
    states = [
        {"code": c, "name": STATE_NAMES.get(c, c), "orders": o, "days": d, "late": l, "score": s}
        for c, o, d, l, s in rows("""
            SELECT customer_state, orders, avg_delivery_days, late_share, avg_score
            FROM mart_states WHERE orders >= 1000 ORDER BY orders DESC""")
    ]
    cohort_rows = rows("""
        SELECT cohort_month, month_offset, customers FROM mart_cohorts
        WHERE cohort_month >= '2017-01-01' ORDER BY 1, 2""")
    cohorts: dict = {}
    for month, offset, n in cohort_rows:
        c = cohorts.setdefault(str(month)[:7], {"month": str(month)[:7], "n": None, "back": [None] * 12})
        if offset == 0:
            c["n"] = n
        elif offset <= 12:
            c["back"][offset - 1] = n
    cohorts = [c for c in cohorts.values() if c["n"] and c["n"] >= 500 and c["month"] <= "2018-07"]
    # A cohort has complete data for k months only if cohort + k is no later than Aug 2018.
    for c in cohorts:
        y, m = map(int, c["month"].split("-"))
        for k in range(1, 13):
            if (y * 12 + m - 1 + k) > (2018 * 12 + 8 - 1):
                c["back"][k - 1] = None
            elif c["back"][k - 1] is None:
                c["back"][k - 1] = 0

    segments = [
        {"name": s, "customers": c, "revenue": r}
        for s, c, r in rows("""
            SELECT segment, COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER (),
                   SUM(monetary) / SUM(SUM(monetary)) OVER ()
            FROM mart_rfm GROUP BY 1 ORDER BY 3 DESC""")
    ]
    reg = findings["delay_regression"]["ols_review_score"]
    drivers = [
        {"label": label, "coef": reg[k]["coef"], "lo": reg[k]["ci95"][0], "hi": reg[k]["ci95"][1]}
        for label, k in [("Delivered late", "late"), ("Items from 2+ sellers", "multi_seller"),
                         ("Each extra item in the order", "n_items"), ("Each extra day of delivery time", "delivery_days")]
    ]
    return {
        "headline": findings["headline"],
        "odds_late": findings["delay_regression"]["logit_low_score_odds_ratio"]["late"],
        "monthly": monthly, "delivery": delivery, "states": states,
        "cohorts": cohorts, "segments": segments, "drivers": drivers,
    }


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    data = build_data(con)
    con.close()
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, default=str))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
