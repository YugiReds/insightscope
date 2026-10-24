# Step 5: Analytics

**Result:** three analytics endpoints that turn 9,999 recalls into monthly trends, reason categories and automatically detected spikes. Tests grew to 93; the Postman collection grew to 25 requests.

**Date:** October 23, 2026 (evening)

## What was built

| File | Job |
| --- | --- |
| `analytics.py` | All the analytics logic, with queries written as plain SQL |
| `tests/test_analytics.py` | 48 new tests |
| `main.py`, `schemas.py` | The three new endpoints and their response shapes |

## The endpoints

| Endpoint | What it returns | Errors |
| --- | --- | --- |
| `GET /analytics/recalls/monthly` | Recalls per month (2018-03 to 2026-10, 104 months), split by class | None |
| `GET /analytics/recalls/reasons?start=&end=` | Recalls per reason category, plus the "Other" share (2.5%) | 422 for a backwards or invalid date |
| `GET /analytics/recalls/spikes` | Months unusually high versus the previous 12, with top reasons and firms | None |

## How spike detection works (the z-score)

For each month, look at the 12 months before it and compute their average and how much they usually wiggle (the standard deviation). Then:

```
z = (this month's count − average) ÷ usual wiggle
```

A month is a spike when **z is above 2**.

**Example:** March 2019 had 535 recalls against an average of about 97 and a wiggle of about 44, so z ≈ 10.

Rules that keep it honest:
- The month is never part of its own baseline.
- A quiet month counts as 0, not missing.
- A month needs a full 12 months of history, and a perfectly flat history can't be scored.

Limits to admit in an interview: "z above 2" is a rule of thumb, and one huge spike inflates the wiggle for the next 12 months, which can hide smaller spikes.

## The six spikes found

2019-03, 2021-06, 2021-11, 2022-06, 2025-04 and 2025-10. In each, one company drives a large share, but not always most of it. In 3 of the 6 the top firm has 57–87% of the month (King Bio Inc. had 465 of March 2019's 535 recalls); in the other 3 it's 41–49%. So "recalls surged" would be misleading, and so would "every spike is one firm's mass recall." Step 6's summaries state the top firm's exact share for each spike.

## Reason categories (keyword rules)

Each free-text reason goes into the **first** category whose keywords match, so the order matters:

1. Sterility / contamination
2. Impurities
3. Potency
4. Labeling
5. CGMP violations (good manufacturing practice)
6. Packaging
7. Failed specifications
8. Unapproved drug
9. Other

Specific problems come before broad ones, so "CGMP Deviations: carcinogen impurity detected" lands in Impurities. The keyword "potent" is avoided because it matches "potential." Claude Code's first draft misfiled hundreds of rows and was fixed by spot-checking real reasons.

## Partial-month detection

The table holds only the newest ~10,000 recalls, so the oldest month may be cut off. Every FDA report in the data is dated on a Wednesday, so any 7 days contain exactly one weekly report. A fully covered month must therefore have a report in its first 7 days. The oldest recall is dated February 21, 2018, so February 2018 is excluded.

## Testing the tests

The tests use made-up data in a temporary table that's rolled back, so real data is never touched. Six deliberate breaks were each caught (for example, including the month in its own baseline failed 7 tests). One weak test was found: with the threshold set to 0 it still passed, so a month with z ≈ 1.9 was added that must **not** be flagged.

## Postman

6 new requests (4 happy path, 2 error cases: backwards date range and invalid date), bringing the collection to 25.

## Git commits in this step

| Commit | Message |
| --- | --- |
| `388937c` | Add recall analytics with tests and Postman requests; stop tracking Postman's YAML copies |
