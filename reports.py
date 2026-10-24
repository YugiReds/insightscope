"""Step 8a: CSV reports (recalls and spike summaries).

Everything here uses only Python's standard `csv` module. There is no PDF code on the server on purpose: the
printable report is made by the browser's own "Print / Save as PDF" (see the README for why).
Each function takes an open database connection and returns the file's bytes plus a safe file name.
"""
import csv
import io
import re

from sqlalchemy import Date, String, bindparam, text

import analytics
import insights

RECALL_COLUMNS = [
    "recall_number", "report_date", "classification", "status", "recalling_firm",
    "product_description", "reason_for_recall", "reason_category",
]
SPIKE_COLUMNS = [
    "month", "recalls", "baseline_average", "z_score", "top_firm", "top_firm_share_pct",
    "top_reasons", "summary", "source", "fallback_reason",
]


# ---------------------------------------------------------------------------------------------------------
# Safety: CSV injection
# ---------------------------------------------------------------------------------------------------------
# A spreadsheet (Excel, Google Sheets) treats a cell that STARTS with = + - @ (or a tab or carriage return) as a
# formula to run, not as text. Our cells hold text from outside our control (firm names, product descriptions,
# AI-written summaries). If one began with "=HYPERLINK(...)", opening the file could run it. This is called CSV
# injection. The standard defence is to put an apostrophe in front: spreadsheets show the cell as plain text and
# hide the apostrophe. We do it for EVERY text cell, including ones that look harmless.
# The cost: a real value that starts with "-" or "+" (like "+Protec Hands Gel", which exists in our data) gets a
# leading apostrophe in the raw file. That is the accepted trade-off.
DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r")


def neutralize(value):
    """Return the cell with a leading apostrophe if a spreadsheet could read it as a formula."""
    if isinstance(value, str) and value.startswith(DANGEROUS_START):
        return "'" + value
    return value  # numbers, dates and None are not text, so they cannot start a formula


# ---------------------------------------------------------------------------------------------------------
# Building the file
# ---------------------------------------------------------------------------------------------------------

def build_csv(columns, rows):
    """A CSV file as bytes: a header row, then one row per item, with every text cell made safe.

    - The csv module adds quotes around any cell with a comma, quote or newline, so text like
      'Quote "Co", Ltd' survives.
    - Rows end with \\r\\n, which spreadsheets expect.
    - "utf-8-sig" means UTF-8 WITH a byte order mark at the start. Excel uses that mark to know the file is UTF-8,
      so names with accents (Müller, Lääke) open correctly instead of as garbled characters.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([neutralize(cell) for cell in row])
    return buffer.getvalue().encode("utf-8-sig")


def download_headers(filename):
    """Tells the browser to save the response as a file instead of showing it. The file name is built only from
    dates and short slugs made by this module (see below), so it can never contain quotes or line breaks."""
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


# ---------------------------------------------------------------------------------------------------------
# Report 1: one row per recall
# ---------------------------------------------------------------------------------------------------------

# The same order as the /recalls endpoint: newest first, and recall_number (unique) breaks ties between recalls
# reported on the same day, so the file is always in exactly the same order.
RECALLS_SQL = text(f"""
    SELECT recall_number, report_date, classification, status, recalling_firm,
           product_description, reason_for_recall,
           {analytics.CATEGORY_SQL} AS reason_category
    FROM recalls
    WHERE (:start IS NULL OR report_date >= :start)
      AND (:end IS NULL OR report_date <= :end)
      AND (:classification IS NULL OR lower(classification) = lower(:classification))
    ORDER BY report_date DESC NULLS LAST, recall_number DESC
""").bindparams(bindparam("start", type_=Date), bindparam("end", type_=Date), bindparam("classification", type_=String))


def recalls_filename(start, end, classification):
    """For example insightscope-recalls_2025-01-01_to_2025-12-31_class-i.csv"""
    if start and end:
        span = f"{start}_to_{end}"
    elif start:
        span = f"from-{start}"
    elif end:
        span = f"until-{end}"
    else:
        span = "all-dates"
    name = f"insightscope-recalls_{span}"
    slug = re.sub(r"[^a-z0-9]+", "-", (classification or "").lower()).strip("-")[:30]  # letters, digits and dashes only
    return f"{name}_{slug}.csv" if slug else f"{name}.csv"


def recalls_csv(conn, start=None, end=None, classification=None):
    """Every recall in the chosen date range (both ends included) and class, as a CSV file."""
    rows = conn.execute(RECALLS_SQL, {"start": start, "end": end, "classification": classification or None}).all()
    return build_csv(RECALL_COLUMNS, rows), recalls_filename(start, end, classification or None)


# ---------------------------------------------------------------------------------------------------------
# Report 2: one row per spike month
# ---------------------------------------------------------------------------------------------------------

def spikes_filename(months):
    if not months:
        return "insightscope-spikes.csv"
    if len(months) == 1:
        return f"insightscope-spikes_{months[0]}.csv"
    return f"insightscope-spikes_{months[0]}_to_{months[-1]}.csv"


def spikes_csv(conn, client):
    """One row per spike. This reuses insights.py, so a summary that is already in the cache is NOT written again
    and does not call the AI. Only a spike with no saved summary can trigger one AI call (then it is saved too).
    The connection must commit afterwards, because new summaries are saved to the cache table."""
    result = insights.spike_insights(conn, client)
    rows = []
    for item in result["spikes"]:
        facts = item["facts"]
        firm = facts["top_recalling_firms"][0] if facts["top_recalling_firms"] else None
        reasons = "; ".join(f"{r['category']} ({r['recalls']})" for r in facts["top_reason_categories"])
        rows.append([
            item["month"],
            facts["recalls"],
            facts["baseline_mean"],
            facts["z_score"],
            firm["recalling_firm"] if firm else "",
            facts["top_firm_share_pct"] if firm else "",
            reasons,
            item["summary"],
            item["source"],
            item["fallback_reason"] or "",
        ])
    return build_csv(SPIKE_COLUMNS, rows), spikes_filename([item["month"] for item in result["spikes"]])
