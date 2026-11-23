Agent 1 batch research patch — safe integration

Do not upload install_batch20.py to Render or run it in the Render container.
1. Download the EXACT app.py and index.html from the GitHub branch Render deploys.
2. Put them in one folder with install_batch20.py and run: python install_batch20.py
3. Upload the patched app.py, index.html and the included research.py to that SAME branch.
4. Commit; confirm Render deploys that commit.
5. Use the new "Research A-list automatically" button. Keep the page open; requests run sequentially.
6. Review the evidence for each candidate. No prospect is independently verified automatically; no outreach or lead import occurs.

Caveats: Public Bing RSS may return zero candidates or rate-limit; slow calls may exceed Render free-tier limits. This is a bounded prototype, not a guaranteed 20-prospect output. Staged licenses must exist in the database. The browser retains batch progress only while the page stays open. Candidate names and phone/email are public-web observations, not confirmed ownership or deliverability. No verification-code bypass.
