"""Recall analytics: monthly counts, reason categories and spike detection.

Every function takes an open database connection and returns plain dicts, and the numbers come from plain SQL
written with text() so each query can be read top to bottom. main.py only calls these functions.
"""
from datetime import date, timedelta

from sqlalchemy import Date, bindparam, text

# ---------------------------------------------------------------------------------------------------------
# Reason categories
# ---------------------------------------------------------------------------------------------------------
# The FDA writes a free-text reason, usually "Headline: details". We sort each reason into one category by
# keyword. The rules are checked IN THIS ORDER and the FIRST match wins, so the order is a real decision:
#   * Specific product problems come first (contamination, impurities, potency, labeling). A reason such as
#     "CGMP Deviations: carcinogen impurity detected" lands in Impurities, which says more than CGMP.
#   * The broad CGMP (good manufacturing practice) bucket comes next, so incidental words inside a CGMP reason
#     ("...repackaged...", "...water leakage...") do not drag it into Packaging.
#   * The weaker catch-alls come last. Anything that matches nothing is "Other".
# Keywords are matched against the lower-cased text. Do NOT use "potent": it also matches "potential".
OTHER = "Other"
REASON_RULES = [
    ("Sterility / contamination",
     "steril|microbial|contaminat|bacteri|mold|fung|endotoxin|particulate|foreign|insanitary|burkholderia"),
    ("Impurities", "impurit|degradation|nitrosamine|ndma|nmba|ndea|carcinogen|benzene"),
    ("Potency", "potency|subpotent|superpotent|sub-potent|super-potent|assay"),
    ("Labeling", "labeling|mislabel|incorrect.{0,20}lot"),
    ("CGMP violations", "gmp|good manufacturing|processing control"),
    ("Packaging", "packag|container|closure|child.resistant|blister|leak"),
    ("Failed specifications", "dissolution|stability|specification|content uniformity"),
    ("Unapproved drug", "without an approved|without approved|unapproved|nda/anda|tainted"),
]
CATEGORY_NAMES = [name for name, _ in REASON_RULES] + [OTHER]


def _category_case_sql(column="reason_for_recall"):
    """Build the SQL CASE expression from REASON_RULES, so the rules are written down in only one place.
    Only our own constants go into this string, never user input."""
    whens = "\n".join(f"        WHEN lower({column}) ~ '{pattern}' THEN '{name}'" for name, pattern in REASON_RULES)
    return f"CASE\n{whens}\n        ELSE '{OTHER}'\n    END"


CATEGORY_SQL = _category_case_sql()

# ---------------------------------------------------------------------------------------------------------
# Spike detection settings
# ---------------------------------------------------------------------------------------------------------
BASELINE_MONTHS = 12      # a month is compared with the 12 months before it
SPIKE_THRESHOLD = 2.0     # flagged when its z-score is above this
TOP_N = 3                 # reason categories and firms listed for each spike

METHOD_DESCRIPTION = (
    f"For each month, take the recall counts of the previous {BASELINE_MONTHS} months and compute their mean and "
    "sample standard deviation. z = (this month's count - mean) / standard deviation. A month is a spike when "
    f"z is above {SPIKE_THRESHOLD}. Months with fewer than {BASELINE_MONTHS} months of history, or a flat "
    "history (standard deviation 0), are not scored."
)


# ---------------------------------------------------------------------------------------------------------
# Which months can we trust?
# ---------------------------------------------------------------------------------------------------------

def _first_of_next_month(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def get_coverage(conn):
    """Work out which months the data covers completely. Returns None if there are no recalls.

    The recalls table holds only the newest ~10,000 recalls, so the load cut the history off at an arbitrary
    point and the OLDEST month may be only partly there. The FDA publishes recalls in weekly reports (every
    report date in our data is a Wednesday), and any 7 consecutive days contain exactly one weekly report.
    So a fully covered month must have a report dated within its first 7 days. If our oldest recall is dated
    after the 7th, at least one weekly report of that month is missing and the month is partial, so we leave it out.

    Limit: the cut can also fall inside a single report date, and then even a month whose oldest recall is
    dated in the first week can be short by some of that day's recalls. That cannot be detected from the data.

    The NEWEST month can be incomplete too (reports still to come). We flag it but keep it: an incomplete month
    is low, so it cannot create a false spike.
    """
    row = conn.execute(text("SELECT MIN(report_date) AS oldest, MAX(report_date) AS newest FROM recalls")).one()
    if row.oldest is None:
        return None
    oldest, newest = row.oldest, row.newest
    oldest_month = oldest.replace(day=1)
    oldest_is_partial = oldest.day > 7
    first_full_month = _first_of_next_month(oldest_month) if oldest_is_partial else oldest_month
    newest_month = newest.replace(day=1)
    # If one more weekly report would still land in the same month, that month may not be finished.
    newest_may_be_incomplete = (newest + timedelta(days=7)).replace(day=1) == newest_month
    return {
        "oldest_report_date": oldest,
        "newest_report_date": newest,
        "first_full_month": first_full_month,
        "newest_month": newest_month,
        "excluded_oldest_month": oldest_month if oldest_is_partial else None,
        "newest_month_may_be_incomplete": newest_may_be_incomplete,
    }


def _coverage_for_response(cov):
    if cov is None:
        return None
    return {
        "oldest_report_date": cov["oldest_report_date"],
        "newest_report_date": cov["newest_report_date"],
        "first_full_month": cov["first_full_month"].strftime("%Y-%m"),
        "excluded_oldest_month": cov["excluded_oldest_month"].strftime("%Y-%m") if cov["excluded_oldest_month"] else None,
        "newest_month_may_be_incomplete": cov["newest_month_may_be_incomplete"],
    }


def _months_between(first, last):
    months = []
    while first <= last:
        months.append(first)
        first = _first_of_next_month(first)
    return months


# ---------------------------------------------------------------------------------------------------------
# 1. Monthly counts by classification
# ---------------------------------------------------------------------------------------------------------

MONTHLY_SQL = text("""
    SELECT CAST(date_trunc('month', report_date) AS date) AS month,
           COALESCE(classification, 'Unknown')            AS classification,
           COUNT(*)                                       AS recalls
    FROM recalls
    WHERE report_date >= :first_month
    GROUP BY 1, 2
    ORDER BY 1, 2
""").bindparams(bindparam("first_month", type_=Date))


def monthly_recalls(conn):
    """Recall counts per month (by report_date), split by classification, for fully covered months only."""
    cov = get_coverage(conn)
    if cov is None or cov["first_full_month"] > cov["newest_month"]:
        return {"coverage": _coverage_for_response(cov), "classifications": [], "months": []}

    rows = conn.execute(MONTHLY_SQL, {"first_month": cov["first_full_month"]}).all()
    classifications = sorted({r.classification for r in rows})
    counts = {}
    for r in rows:
        counts.setdefault(r.month, {})[r.classification] = r.recalls

    months = []
    for month in _months_between(cov["first_full_month"], cov["newest_month"]):  # include months with no recalls
        by_class = {c: counts.get(month, {}).get(c, 0) for c in classifications}
        months.append({"month": month.strftime("%Y-%m"), "total": sum(by_class.values()), "by_classification": by_class})
    return {"coverage": _coverage_for_response(cov), "classifications": classifications, "months": months}


# ---------------------------------------------------------------------------------------------------------
# 2. Reason categories
# ---------------------------------------------------------------------------------------------------------

_RANGE_FILTER = "(:start IS NULL OR report_date >= :start) AND (:end IS NULL OR report_date <= :end)"
_RANGE_PARAMS = (bindparam("start", type_=Date), bindparam("end", type_=Date))

REASONS_SQL = text(f"""
    SELECT {CATEGORY_SQL} AS category,
           COUNT(*)       AS recalls
    FROM recalls
    WHERE {_RANGE_FILTER}
    GROUP BY 1
""").bindparams(*_RANGE_PARAMS)

# The most common reasons that matched no rule. This is how you judge whether the rules need work.
TOP_OTHER_SQL = text(f"""
    SELECT left(regexp_replace(reason_for_recall, '\\s+', ' ', 'g'), 120) AS reason,
           COUNT(*)                                                        AS recalls
    FROM recalls
    WHERE {_RANGE_FILTER}
      AND reason_for_recall IS NOT NULL
      AND {CATEGORY_SQL} = '{OTHER}'
    GROUP BY 1
    ORDER BY recalls DESC, reason
    LIMIT 5
""").bindparams(*_RANGE_PARAMS)


def reason_categories(conn, start=None, end=None):
    """Recall counts per reason category for report dates from start to end (both inclusive, both optional)."""
    params = {"start": start, "end": end}
    counts = {r.category: r.recalls for r in conn.execute(REASONS_SQL, params)}
    total = sum(counts.values())

    def share(n):
        return round(n / total, 4) if total else 0.0

    # Every category is listed, even with 0 recalls. Biggest first, ties by name so the order is always the same.
    categories = sorted(
        ({"category": name, "recalls": counts.get(name, 0), "share": share(counts.get(name, 0))} for name in CATEGORY_NAMES),
        key=lambda c: (-c["recalls"], c["category"]),
    )
    other_reasons = [{"reason": r.reason, "recalls": r.recalls} for r in conn.execute(TOP_OTHER_SQL, params)]
    return {
        "start": start,
        "end": end,
        "total": total,
        "categories": categories,
        "other_share": share(counts.get(OTHER, 0)),
        "top_other_reasons": other_reasons,
    }


# ---------------------------------------------------------------------------------------------------------
# 3. Spike detection
# ---------------------------------------------------------------------------------------------------------

# Step by step:
#   months   one row per calendar month from the first covered month to the last (months with no recalls are kept)
#   counts   recalls per month, 0 for a quiet month
#   scored   for each month, the mean, standard deviation and size of the window "12 months before this one"
#            (ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING never includes the month itself)
#   final    z = (count - mean) / sd, only for months that have a full 12-month window. NULLIF turns a flat history
#            (sd = 0) into NULL instead of a divide-by-zero error.
SPIKE_SQL = text(f"""
    WITH months AS (
        SELECT CAST(g AS date) AS month
        FROM generate_series(CAST(:first_month AS date), CAST(:last_month AS date), INTERVAL '1 month') AS g
    ),
    counts AS (
        SELECT m.month, COUNT(r.recall_number) AS recalls
        FROM months m
        LEFT JOIN recalls r ON CAST(date_trunc('month', r.report_date) AS date) = m.month
        GROUP BY m.month
    ),
    scored AS (
        SELECT month, recalls,
               AVG(recalls)         OVER w AS baseline_mean,
               STDDEV_SAMP(recalls) OVER w AS baseline_sd,
               COUNT(*)             OVER w AS baseline_size
        FROM counts
        WINDOW w AS (ORDER BY month ROWS BETWEEN {BASELINE_MONTHS} PRECEDING AND 1 PRECEDING)
    )
    SELECT month, recalls, baseline_mean, baseline_sd,
           (recalls - baseline_mean) / NULLIF(baseline_sd, 0) AS z_score
    FROM scored
    WHERE baseline_size = {BASELINE_MONTHS}
    ORDER BY month
""").bindparams(bindparam("first_month", type_=Date), bindparam("last_month", type_=Date))

_IN_MONTH = "report_date >= :month AND report_date < CAST(:month AS date) + INTERVAL '1 month'"

# Ties are broken by name so the same month always gives the same top 3.
TOP_REASONS_SQL = text(f"""
    SELECT {CATEGORY_SQL} AS category, COUNT(*) AS recalls
    FROM recalls
    WHERE {_IN_MONTH}
    GROUP BY 1
    ORDER BY recalls DESC, category
    LIMIT {TOP_N}
""").bindparams(bindparam("month", type_=Date))

TOP_FIRMS_SQL = text(f"""
    SELECT recalling_firm, COUNT(*) AS recalls
    FROM recalls
    WHERE {_IN_MONTH} AND recalling_firm IS NOT NULL
    GROUP BY 1
    ORDER BY recalls DESC, recalling_firm
    LIMIT {TOP_N}
""").bindparams(bindparam("month", type_=Date))


def recall_spikes(conn):
    """Months whose recall count is unusually high compared with the 12 months before them (z above 2)."""
    cov = get_coverage(conn)
    response = {
        "method": METHOD_DESCRIPTION,
        "threshold": SPIKE_THRESHOLD,
        "baseline_months": BASELINE_MONTHS,
        "months_scored": 0,
        "coverage": _coverage_for_response(cov),
        "spikes": [],
    }
    if cov is None or cov["first_full_month"] > cov["newest_month"]:
        return response

    rows = conn.execute(SPIKE_SQL, {"first_month": cov["first_full_month"], "last_month": cov["newest_month"]}).all()
    scored = [r for r in rows if r.z_score is not None]
    response["months_scored"] = len(scored)
    for r in scored:
        if float(r.z_score) <= SPIKE_THRESHOLD:
            continue
        reasons = conn.execute(TOP_REASONS_SQL, {"month": r.month}).all()
        firms = conn.execute(TOP_FIRMS_SQL, {"month": r.month}).all()
        response["spikes"].append({
            "month": r.month.strftime("%Y-%m"),
            "recalls": r.recalls,
            "baseline_mean": round(float(r.baseline_mean), 2),
            "baseline_stddev": round(float(r.baseline_sd), 2),
            "z_score": round(float(r.z_score), 2),
            "top_reason_categories": [{"category": x.category, "recalls": x.recalls} for x in reasons],
            "top_recalling_firms": [{"recalling_firm": x.recalling_firm, "recalls": x.recalls} for x in firms],
        })
    return response
