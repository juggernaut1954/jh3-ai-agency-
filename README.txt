JH III AI REVENUE AGENCY — AGENT 1 FOUNDATION

DEPLOY (GitHub version-3-testing branch)
1. Back up the current GitHub files first.
2. Replace repository root app.py and index.html with the two files here.
3. ADD discovery.py in the same repository root (new required file).
4. Keep security.py, requirements.txt, render.yaml and Render environment variables unchanged.
5. Commit all three files together. Wait for the matching commit to show Live in Render.
6. Sign into the dashboard and find 'Agent 1 · Discover businesses'.
7. Choose Huntsville / Plumbing / 10; tap Find businesses. Review each source before importing one candidate.
8. Test importing the same business twice; the second attempt must be rejected.

FUNCTIONALITY
- Free OSM/Overpass public business listing lookup; no paid keys.
- 3 initial regions, 8 OSM-tagged industry categories; configuration extensible in discovery.py.
- Search preview is read-only; imports require a manual confirmation.
- Preview flags existing leads and do-not-contact statuses using the existing duplicate matcher.
- Import rechecks duplicates under the existing database lock.
- Preserves existing routes, database schema, drafts, replies, security integration.
- No automatic email sending, email validation, qualification or scheduled scraping.

LIMITATIONS
- Not 'any industry' yet: only 8 supported categories. Extend INDUSTRIES mappings for more.
- Not 'any city' yet: only 3 preset search bounding boxes. Extend MARKETS for more.
- Public data coverage can be sparse, stale or missing email/website information.
- OpenStreetMap data attribution required; public Overpass instances may rate-limit or fail.
- No live provider request was possible in the offline test environment; verify after deployment.
- Contact details from public listings are NOT verified. Comply with relevant outreach laws.
- This is an early foundation, not a production-grade multi-provider discovery system.
