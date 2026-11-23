JH III Agent 1 - coverage and website enrichment update

Deploy together on version-3-testing: app.py, index.html, discovery.py.
Dockerfile already copies these files; leave security.py and database untouched.

Changes:
- Additional OSM category tags and removal of arbitrary 120-element output cap.
- Contact completeness ranking; captures phone numbers from public OSM tags.
- Optional Check website button for HTTPS business homepages already listed in OSM.
- Reads at most 100 KB, five-second timeout, no redirects, public-IP checks.
- Extracts only mailto: and tel: links on homepage, not guessed emails.
- Keeps human-reviewed import, duplicate prevention, opt-outs and source attribution.

Limitations:
- Still uses OSM/Overpass only; independent Overture Maps integration is a future phase.
- A website without HTTPS is not crawled. Website contacts are unverified.
- Homepage-only; does not crawl contact pages, social networks, or search engines.
- Free OSM data may remain sparse for HVAC. 20 results is a target, not a promise.
- URL/IP checks mitigate SSRF but are not a complete network sandbox.

Test:
1. Commit three files and wait for Render Deploy live.
2. Search Huntsville HVAC 20; inspect results.
3. For a result with a listed HTTPS website, tap Check website.
4. Review its source and contact details before import.
5. Verify duplicate and opt-out protections remain effective.
