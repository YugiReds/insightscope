"""Run the integrity checks in checks.sql against the database and print PASS/FAIL for each.

Run with:  .\\venv\\Scripts\\python.exe run_checks.py
"""
import sys

from sqlalchemy import text

from db import get_engine


def main():
    # checks.sql holds several SELECT statements separated by semicolons.
    statements = [s.strip() for s in open("checks.sql").read().split(";") if "SELECT" in s]
    failed = False
    with get_engine().connect() as conn:  # read-only: we only run SELECTs
        for stmt in statements:
            name, severity, bad_rows = conn.execute(text(stmt)).one()
            # A nonzero count is reported as the check's severity: FAIL or WARN.
            status = "PASS" if bad_rows == 0 else severity
            # Only real failures make the script exit with an error. Warnings do not.
            failed = failed or status == "FAIL"
            print(f"{status}  {name}: {bad_rows} rows")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
