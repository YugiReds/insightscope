# InsightScope Documentation

This folder explains the whole project in plain language: what was built, step by step, what each file does, and how to fix common problems.

| Folder | What's in it | Read it when |
| --- | --- | --- |
| [1-step-logs](1-step-logs/) | One log per build step: what was done, why, the commands, and what came out of it | You want to remember how something was built |
| [2-file-guide](2-file-guide/) | One guide per important file: its job, the key lines, and why they matter | You want to understand or change a file |
| [3-troubleshooting](3-troubleshooting/) | Errors you might hit and how to fix each one | Something is broken |

## The steps at a glance

| Step | What it added | Status |
| --- | --- | --- |
| [0. Setup](1-step-logs/00-setup.md) | Tools, project folder, Git, GitHub | Done |
| [1. Data pipeline](1-step-logs/01-data-pipeline.md) | 5,000 FDA drug records in PostgreSQL, plus data checks | Done |
| [2. API](1-step-logs/02-api.md) | FastAPI endpoints, automated tests, README | Done |
| [3. Postman](1-step-logs/03-postman.md) | A saved Postman collection that tests the API | Done |
| [4. Recalls](1-step-logs/04-recalls.md) | 9,999 FDA recalls, recall endpoints, the N/A bug fix | Done |
| [5. Analytics](1-step-logs/05-analytics.md) | Monthly trends, reason categories, spike detection | Done |
| [6. AI insights](1-step-logs/06-ai-insights.md) | AI-written summaries of each spike, fact-checked (Hugging Face) | Done |
| [7. Dashboard](1-step-logs/07-dashboard.md) | React page with charts, spike summaries, NDC lookup and a live status light | Done |
| 8. Reports and deploy | Report export and a live link | Next |

Setup is step 0 so the numbers match the ones used in `CLAUDE.md`, the README and the Claude Code prompts.

## How this folder stays current

After each step finishes, its log gets filled in, the file guide gets entries for any new or changed files, and the troubleshooting guide gets any new problems we hit. A new step gets a new log file (`08-reports-deploy.md`, and so on).

This Markdown version lives in `documentation/documentation-github/` (committed to GitHub). The same files as PDFs live in `documentation/documentation/` (kept on your PC only, ignored by Git).

A note on screenshots: these guides use code snippets copied from the real files instead of screenshots. Snippets stay accurate when you search for them in VS Code (`Ctrl+F`), and they don't go stale the way images do.
