# JH III AI Revenue Agency — Secure Mobile Cloud MVP

A **deployable**, mobile-responsive three-workflow dashboard. It is **not hosted yet**. Hosting requires a Render account and deployment. No desktop is required for normal use after deployment.

## Features
- Administrator password sign-in; signed, 12-hour secure HTTP-only session cookie.
- CSRF protection for all state-changing requests; origin check; basic login throttling; security headers.
- Persistent SQLite database on an attached cloud disk; CSV imports and exports; lead scoring; draft approval; reply classification and opt-out blocking.
- Mobile browser layout; cloud runs independently of your phone.

## Deploy to Render (from Android browser)
1. Create a **private GitHub repository** and upload the files in this folder (not the ZIP itself). Never commit credentials or customer data.
2. Log in to Render, choose **New → Blueprint**, connect the private repository, and apply `render.yaml`.
3. When prompted for `ADMIN_PASSWORD`, enter a **unique password of at least 16 characters**. `SESSION_SECRET` is generated automatically.
4. Select a paid plan supporting a persistent disk. A free ephemeral service would lose the SQLite database on restart.
5. Wait for the service to deploy, then open its `https://...onrender.com` URL on Android and sign in.
6. Add real verified prospects or import CSV; generate drafts, approve them and manually send them from your own email provider.
7. Back up lead data using **Export CSV** regularly. Export is not a full backup of drafts/replies/audit; use provider disk backups or database snapshots for disaster recovery.

**Never publish the password or session secret.** Use HTTPS, restrict repository access, enable 2FA on GitHub and Render, and keep dependencies updated. Use a real external rate limiter / WAF for stronger brute-force protection; the included in-process limiter resets on restart and is not multi-instance safe. This is a single-user MVP, not audited enterprise-grade security. No encrypted-at-rest database, MFA, or fine-grained user roles.

## Run locally (optional)
```bash
export SESSION_SECRET='replace-with-random-secret-at-least-32-characters'
export ADMIN_PASSWORD='replace-with-unique-password-at-least-16-chars'
pip install -r requirements.txt
uvicorn app:app --reload
```
Local HTTP login sets secure cookies, so use HTTPS or adjust secure cookie flags for development only. The deployed HTTPS environment is the intended target.

## What is NOT connected
No live business search, no LLM calls, no Gmail inbox, no sending email, no automated prospect discovery. These are **rule-based workflows**, not fully autonomous AI agents. Outbound messaging is always manually sent. Comply with CAN-SPAM, opt-outs, and privacy laws.

## Database
SQLite at `JH3_DB`, default local `agency.db`, Render disk `/data/agency.db`. Use one web instance; do not horizontally scale SQLite writes.
