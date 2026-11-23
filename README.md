# Agent 1 Alabama licensing integration

## Files
- `app.py` and `index.html`: replacements for the two supplied files, preserving existing routes and UI and adding a licensing staging/review workflow.
- `collector.py`: standalone Playwright collector prototype, not yet tested against live Alabama search results.
- `requirements-collector.txt`: local collector requirements; do not add Playwright to Render.

## Installation
1. Commit the replacement `app.py` and `index.html` to the `version-3-testing` branch in the same locations as the existing files. Keep `discovery.py`, `security.py`, Dockerfile, and existing requirements unchanged.
2. Render redeploys. Open the dashboard and find **Agent 1 · Alabama license records**.
3. On a desktop with Python 3.10+, run `pip install -r requirements-collector.txt`, `python -m playwright install chromium`, and `python collector.py --letter B`.
4. In the browser, enter the letter and verification code manually, submit, then press Enter in the terminal. The collector tries to click Next and saves `alabama_licenses.csv` after each page.
5. Upload that CSV in the dashboard, review entries, verify the company city/contact information, and import selected active contractor records.

## Limits
- The collector is **not hosted** on Render; a cloud page cannot display an interactive verification challenge in a local browser automatically.
- Pagination selectors are unverified against the live website; the collector will stop if the site differs.
- Staged licensing records are separate from leads; nothing is emailed.
- Duplicate license numbers are updated rather than inserted twice, except reviewed/conflicting holder records are skipped. Business-level duplicates are checked by existing lead logic, but names differing across licenses can still require human reconciliation.
- The list API currently displays the first 200 staged records. For larger sets, add pagination before operational use.
- Test on a staging Render service and back up the database before replacing production files.
