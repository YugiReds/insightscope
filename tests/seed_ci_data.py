"""MADE-UP DATA FOR CI ONLY. Nothing here is real FDA data: every firm, drug and recall is invented.

Why it exists: the GitHub Actions workflow needs a database that is filled with data, but loading the real openFDA data
on every push would be slow, could be rate limited, and would change from week to week (so a test could fail with no
code change). This script builds a small fixed data set instead. It uses no random numbers and no "today", so every run
produces exactly the same rows.

What the data is shaped to contain (because tests look for it):
  * products: repeated NDCs whose label versions have different dates, several labelers, a null labeler and a null brand
  * recalls: weekly reports on one weekday (Wednesday) for more than two years, a quiet baseline with two big spikes,
    a recall numbered 'N/A', null states and null voluntary/mandated values, cells that start with + or =, a firm
    with a comma, a reason with a quote, firm names with % and _, and one NDC with more than ten recalls

SAFETY: this script deletes every row in the product and recall tables before it inserts. So it REFUSES to run unless
the database name in DATABASE_URL is exactly "insightscope_ci". It never reads .env, so it cannot be pointed at your
real database (or Neon) by accident. Create the throwaway database yourself first, then:

    $env:DATABASE_URL = "postgresql://user:password@localhost:5432/insightscope_ci"
    .\\venv\\Scripts\\python.exe tests\\seed_ci_data.py
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

CI_DATABASE_NAME = "insightscope_ci"


class SeedRefused(Exception):
    """The safety check said no. The message never contains the database address (it holds the password)."""


def ensure_ci_database(url):
    """Raise SeedRefused unless `url` names the database insightscope_ci (exactly, capitals and all)."""
    if not url or not url.strip():
        raise SeedRefused(
            "DATABASE_URL is not set. Set it in the shell to the throwaway database "
            f"'{CI_DATABASE_NAME}'. This script never reads .env. Nothing was changed."
        )
    from sqlalchemy.engine import make_url  # only parses the text, it does not connect
    try:
        name = make_url(url.strip()).database
    except Exception:
        raise SeedRefused("DATABASE_URL could not be read as a database address. Nothing was changed.") from None
    if name != CI_DATABASE_NAME:
        raise SeedRefused(
            f"Refusing to run: the database name in DATABASE_URL must be exactly '{CI_DATABASE_NAME}', because this "
            "script deletes every row in the product and recall tables. Nothing was changed."
        )


# ---------------------------------------------------------------------------------------------------------
# The made-up data (pure functions: no database, no randomness, no clock)
# ---------------------------------------------------------------------------------------------------------

LABELERS = ["Example Pharma Inc", "Sample Labs LLC", "Fictional Meds Co", "Placeholder Health Ltd",
            "Demo Generics Corp", "Test Remedies Inc"]

# (product NDC, brand, generic, labeler number, dosage form). Labeler 0 has the most NDCs so the top-5 list has a clear order.
PRODUCT_NDCS = [
    ("60001-101", "Examplin", "Exampleamine", 0, "TABLET"),
    ("60001-102", "Samplex", "Sampleazole", 0, "CAPSULE"),
    ("60001-103", "Demoprin", "Demoprofen", 0, "TABLET"),
    ("60001-104", "Madeupol", "Madeuptamol", 0, "SOLUTION"),
    ("60002-201", "Fictosan", "Fictosamine", 1, "TABLET"),
    ("60002-202", "Placebon", "Placebamide", 1, "INJECTION"),
    ("60002-203", "Notrealin", "Notrealamine", 1, "TABLET"),
    ("60003-301", "Pretendol", "Pretendazole", 2, "TABLET"),
    ("60003-302", "Fakezyme", "Fakezymide", 2, "CAPSULE"),
    ("60004-401", "Mockacin", "Mockacillin", 3, "TABLET"),
    ("60005-501", "Dummyvir", "Dummyvirine", 4, "TABLET"),
    ("60006-601", "Illustrix", "Illustratin", 5, "CREAM"),
]

# Extra, OLDER label versions of some NDCs: (ndc, spl id, start date). The newest version of each NDC is the base row.
# 60001-101 has three dates, 60003-301 has an older version with NO date (it must lose to the dated one).
OLDER_VERSIONS = [
    ("60001-101", "spl-b", date(2021, 3, 1)),
    ("60001-101", "spl-c", date(2019, 1, 15)),
    ("60001-102", "spl-b", date(2020, 2, 2)),
    ("60003-301", "spl-b", None),
]
LATEST_START = date(2023, 5, 1)

FIRST_REPORT = date(2024, 1, 3)       # a Wednesday, inside the first 7 days of its month
LAST_REPORT = date(2026, 3, 25)       # a Wednesday; a report a week later would fall in the next month
PER_WEEK = 3                          # recalls in each weekly report
# Two Wednesdays that each carry 30 extra recalls, so two months stand out as spikes. They are 13 months apart, so the
# first spike is not in the 12-month baseline of the second one (otherwise it would hide it).
SPIKE_REPORTS = (date(2025, 2, 12), date(2026, 3, 11))
SPIKE_EXTRA = 30
NA_REPORT = date(2025, 6, 4)          # a Wednesday: the report that holds the recall numbered 'N/A'

FIRMS = ["Example Pharma Inc", "Sample Labs LLC", "Fictional Meds Co", "Placeholder Health Ltd", "Demo Generics Corp",
         "Test Remedies Inc", "100% Example Compounding", "Test_Lab Example Co", "Nowhere Pharmacy Group", "Imaginary Rx LLC"]

# Twenty reasons, one per slot; the one at the end matches no keyword rule, so "Other" stays at 5%.
REASONS = [
    "Lack of Sterility Assurance: vials may be contaminated with bacteria",
    "Presence of Particulate Matter: glass particles found in vials",
    "Impurities: nitrosamine impurity above the acceptable limit",
    "Subpotent Drug: assay result below the labeled strength",
    "Labeling: incorrect strength printed on the carton",
    "CGMP Deviations: the firm did not follow good manufacturing practice",
    "Packaging: defective container closure allows leakage",
    "Failed Dissolution Specification at the 12 month stability time point",
    "Unapproved Drug: marketed without an approved application",
    "Lack of Sterility Assurance: vials may be contaminated with bacteria",
    "Impurities: nitrosamine impurity above the acceptable limit",
    "Subpotent Drug: assay result below the labeled strength",
    "Labeling: incorrect strength printed on the carton",
    "CGMP Deviations: the firm did not follow good manufacturing practice",
    "Packaging: defective container closure allows leakage",
    "Failed Dissolution Specification at the 12 month stability time point",
    "Unapproved Drug: marketed without an approved application",
    "CGMP Deviations: the firm did not follow good manufacturing practice",
    "Labeling: incorrect strength printed on the carton",
    "Expiration date printed incorrectly on the outer carton",
]
STATES = ["CA", "NY", "TX", "FL", "OH", "PA", "IL", "NJ"]
CLASSES = ["Class I", "Class II", "Class II", "Class III"]
STATUSES = ["Ongoing", "Completed", "Terminated"]
POPULAR_NDC = "70001-101"             # recalled more than ten times, so paging through its recalls means something


def build_products():
    """(products, active_ingredients, packages) as lists of dicts, ready to insert."""
    products, ingredients, packages = [], [], []

    def add_version(ndc, brand, generic, labeler, form, spl, start):
        product_id = f"{ndc}_{spl}"
        products.append({
            "product_id": product_id, "product_ndc": ndc, "brand_name": brand, "generic_name": generic,
            "labeler_name": labeler, "dosage_form": form, "route": "ORAL", "product_type": "HUMAN PRESCRIPTION DRUG",
            "marketing_category": "ANDA", "application_number": "ANDA000000", "finished": True,
            "marketing_start_date": start, "marketing_end_date": None, "pharm_class": "Made-Up Class [EPC]",
        })
        ingredients.append({"product_id": product_id, "name": (generic or "UNNAMED").upper(), "strength": "10 mg/1"})
        packages.append({"product_id": product_id, "package_ndc": f"{ndc}-1", "description": "30 TABLET in 1 BOTTLE",
                         "marketing_start_date": start, "marketing_end_date": None, "sample": False})

    for ndc, brand, generic, labeler_number, form in PRODUCT_NDCS:
        add_version(ndc, brand, generic, LABELERS[labeler_number], form, "spl-a", LATEST_START)
    for ndc, spl, start in OLDER_VERSIONS:
        base = next(p for p in PRODUCT_NDCS if p[0] == ndc)
        add_version(ndc, base[1], base[2], LABELERS[base[3]], base[4], spl, start)
    # Two rows with gaps, as in the real data: a missing brand, and a missing labeler and dosage form.
    add_version("60007-701", None, "Gapazole", LABELERS[2], "TABLET", "spl-a", LATEST_START)
    add_version("60008-801", "Blankin", "Blankamide", None, None, "spl-a", LATEST_START)
    return products, ingredients, packages


def report_dates():
    """Every Wednesday from FIRST_REPORT to LAST_REPORT."""
    day = FIRST_REPORT
    while day <= LAST_REPORT:
        yield day
        day += timedelta(days=7)


def build_recalls():
    """(recalls, recall_ndcs) as lists of dicts, ready to insert."""
    recalls, recall_ndcs = [], []

    def add_recall(index, report_date, number=None):
        firm = FIRMS[(index * 7) % len(FIRMS)]
        reason = REASONS[index % len(REASONS)]
        description = f"Example Tablets {10 * (index % 5 + 1)} mg, 30 count (made-up product)"
        if index == 20:
            description = "+Example Pain Relief Gel 1% (made-up product)"        # starts with +, a CSV formula character
        if index == 21:
            description = "=Example Cream 2% (made-up product)"                  # starts with =
        if index == 10:
            firm = "Fictional Meds, Inc."                                          # a comma in the firm name
            reason = 'Labeling: the carton says "Take once daily" but should say weekly'   # a quote in the reason
        number = number or f"D-{index + 1:04d}-{report_date.year}"
        recalls.append({
            "recall_number": number,
            "recalling_firm": firm,
            "product_description": description,
            "reason_for_recall": reason,
            "classification": CLASSES[index % len(CLASSES)],
            "status": STATUSES[index % len(STATUSES)],
            "voluntary_mandated": None if index % 5 == 0 else "Voluntary: Firm initiated",
            "distribution_pattern": "Nationwide (made-up)",
            "state": None if index % 7 == 0 else STATES[index % len(STATES)],
            "country": "United States",
            "recall_initiation_date": report_date - timedelta(days=10),
            "report_date": report_date,
        })
        return number

    index = 0
    numbers = []
    for report in report_dates():
        for _ in range(PER_WEEK + (SPIKE_EXTRA if report in SPIKE_REPORTS else 0)):
            numbers.append(add_recall(index, report))
            index += 1
        if report == NA_REPORT:
            add_recall(index, report, number="N/A")      # not added to `numbers`, so it lists no NDCs
            index += 1

    # Which NDCs each numbered recall lists. Most list none (as in the real data).
    listed = {}
    for position, number in enumerate(numbers):
        ndcs = set()
        if position % 9 == 0:
            ndcs.add(POPULAR_NDC)
        elif position % 4 == 1:
            ndcs.add(f"70002-{200 + position % 25}")
        listed[number] = ndcs
    listed[numbers[5]] |= {"70003-301", "70003-302", "70003-303"}      # one recall with several NDCs
    listed[numbers[13]].add("60001-101")                                # one NDC that also exists in products
    for number in numbers:
        for ndc in sorted(listed[number]):
            recall_ndcs.append({"recall_number": number, "product_ndc": ndc})
    return recalls, recall_ndcs


def build_data():
    """All the rows, keyed by table name."""
    products, ingredients, packages = build_products()
    recalls, recall_ndcs = build_recalls()
    return {"products": products, "active_ingredients": ingredients, "packages": packages,
            "recalls": recalls, "recall_ndcs": recall_ndcs}


# ---------------------------------------------------------------------------------------------------------
# Writing it to the database
# ---------------------------------------------------------------------------------------------------------

def main():
    try:
        ensure_ci_database(os.environ.get("DATABASE_URL"))      # BEFORE importing db, which would read .env if the variable were missing
    except SeedRefused as error:
        print(error, file=sys.stderr)
        return 1

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so `import db` works when run as tests\seed_ci_data.py
    import db
    import insights

    engine = db.get_engine()
    db.metadata.create_all(engine)                # only creates what is missing, like the app's own startup
    db.recalls_metadata.create_all(engine)
    data = build_data()
    with engine.begin() as conn:                  # one transaction: all of it, or none of it
        conn.execute(insights.CREATE_CACHE_SQL)
        for table in (db.recall_ndcs, db.recalls, db.active_ingredients, db.packages, db.products):   # children first
            conn.execute(table.delete())
        for table in (db.products, db.active_ingredients, db.packages, db.recalls, db.recall_ndcs):   # parents first
            conn.execute(table.insert(), data[table.name])
    print("Seeded made-up CI data: " + ", ".join(f"{len(rows)} {name}" for name, rows in data.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
