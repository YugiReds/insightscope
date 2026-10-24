# Step 8a: Reports

**Result:** two CSV downloads (recalls for a date range, and the spikes with their summaries) and a clean printable report saved through the browser's "Save as PDF". No new package was installed. Tests grew to 202 Python and 64 dashboard tests, and the Postman collection grew to 30 requests.

**Date:** October 24, 2026 (early morning)

## The goal

Let people take the data away: a spreadsheet for analysts and a PDF for anyone who just wants to read it. In a real support or analyst job, "can I get this in Excel?" is one of the first things people ask for.

## What was built

| Piece | What it does |
| --- | --- |
| `GET /reports/recalls.csv` | One row per recall, newest first (`recall_number` breaks ties). Optional `start`, `end` and `classification` filters. 422 for a backwards or invalid date range |
| `GET /reports/spikes.csv` | One row per spike: month, count, baseline average, z-score, top firm and its share, top reasons, summary, source and fallback reason |
| "Download report" area in the dashboard | A button for each CSV, plus **Print / Save as PDF**. The recalls button follows the date range picked under the reasons chart |
| Printed page | Title, date generated, date range, headline numbers, the chart, the spike summaries with AI/Template badges, reason categories and the data limits. Buttons, lookup, date pickers and the status light are hidden |

Downloaded files get descriptive names, such as `insightscope-recalls_2025-01-01_to_2025-12-31_class-i.csv`.

## Decisions worth explaining in an interview

**Print-to-PDF instead of a server PDF library.** Server PDF libraries usually need extra system software that's awkward to install on cloud hosts, so this keeps the deploy (step 8b) simple. It also means one design for screen and paper. The trade-off: no scheduled or emailed PDFs.

**CSV injection protection.** A spreadsheet runs any cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return as a formula. Our cells hold text we don't control (firm names, product descriptions, AI text), so every such cell gets a leading apostrophe, and Excel then shows it as plain text. This isn't theoretical: a real product in the data starts with `+` ("+Protec Hands Antibacterial Gel").

**UTF-8 with a byte order mark (BOM).** It's an invisible marker at the start of the file that tells Excel the file is UTF-8, so accented firm names display correctly.

**The spikes CSV reuses the AI cache.** Spikes that already have a saved summary cause no AI call and cost nothing. Only a spike with no saved summary would trigger one call.

**Downloads that explain failures.** The dashboard fetches the file itself instead of using a plain link, so if the API is down or rejects the dates, you see the same plain-language error and **Try again** as everywhere else, instead of a broken download.

## The print bug story

All the tests passed, but printing the real page through Chrome's print engine found three problems the tests missed:

| Problem | Cause | Fix |
| --- | --- | --- |
| **The chart was missing from the printout** | A print rule (`max-width: 100%`) collapsed it: Recharts draws inside a box that measures zero width when the browser switches to print layout | While printing, charts get a fixed width (620 px), switched on just before printing (`ChartFrame.jsx`) |
| Pages left half empty | A "keep each section together" rule pushed tall sections onto new pages | Removed it |
| Cards too tall | Screen-sized text | Smaller print text. The report now fits on 4 pages |

The light-screen and dark-screen printouts came out identical (4 pages each), so the screen mode doesn't affect the paper.

**The lesson:** tests check the code's logic, but only looking at the real output catches layout problems. This is a good "tell me about a bug" interview story.

## Testing the tests

Python, 8 deliberate breaks, all caught:

| Break | Tests that failed |
| --- | --- |
| Injection guard removed | 10 |
| End-date filter ignored | 5 |
| Byte order mark removed | 4 |
| Classification filter ignored | 3 |
| Sorted oldest first | 3 |
| Tiebreaker removed | 2 |
| Summary cache ignored | 2 |
| Backwards-range check removed | 1 |

Dashboard, 13 deliberate breaks, all caught. Examples: print button does nothing (1), recalls link ignores the range (3), dark colours used in print (1), failed download silently ignored (3), charts not fixed-size for printing (2), and the chart-collapsing rule put back (1).

Claude Code's first attempts at the two filter breaks crashed on import, which proves nothing, so it redid them properly. A break only counts if the code still runs and a test catches the wrong behaviour.

Postman: the collection's test scripts ran against the live server with 0 failures, and 5 failed against a deliberately wrong copy.

## Not checked

- Chrome's on-screen print dialog itself (only its print engine), A4 paper, and browsers other than Chrome.
- Opening a CSV in real Excel (the file's bytes were checked, not Excel's display).
- A real browser download from the buttons (the dashboard tests fake the file save).
- A printout with a Template-summary card or a custom date range (covered by tests, not read on paper).

## How to use it

Restart your API if it isn't running with `--reload`, or the `/reports` endpoints won't exist yet.

- **CSV:** use the buttons in **Download report**, or open `http://127.0.0.1:8000/reports/spikes.csv` directly.
- **PDF:** click **Print / Save as PDF**, choose **Save as PDF** as the printer, and turn off **Headers and footers** for a cleaner page.

## Git commits in this step

| Commit | Message |
| --- | --- |
| `6c2e8b1` | Add CSV reports and printable PDF report, with tests; step 8a docs |

## Interview lines

- "Exports protect against CSV injection, because the cells hold text we don't control, and one real product name already starts with a plus sign."
- "I chose browser print-to-PDF over a server PDF library to keep deployment simple, and I can name the trade-off: no scheduled PDFs."
- "All the tests passed, but the chart was missing from the printed PDF. Checking the real output found it, so I added a regression test for that exact rule."
