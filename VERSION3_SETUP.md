# JH III AI Agency — Version 3 upgrade

## What is new
- Persistent PostgreSQL using `DATABASE_URL` (Supabase recommended)
- OpenAI Responses API for outreach drafts and reply classification
- Opt-out override and human approval retained
- `GET /api/system-status` reports database and AI mode after login
- Existing dashboard and API endpoints preserved
- No automatic outbound emails or web scraping

## Deploy from Android
1. Download the ZIP, extract it, and replace the matching files in your **existing** private GitHub repository. Keep the files at repository root, not in a nested folder. Commit the changes. Do **not** create a second Render service.
2. Create a Supabase project at https://supabase.com/dashboard . In its **Connect** dialog, copy the **Session pooler** PostgreSQL connection string (port 5432). Render may require an IPv4-capable pooler; do not use the direct IPv6 connection if unsupported. Replace the placeholder database password in the connection string. URL-encode special characters in the password if necessary. Do not share this string or commit it to GitHub.
3. In your existing Render web service > Environment, add `DATABASE_URL` with the full PostgreSQL connection string, and `OPENAI_API_KEY` with your API key from https://platform.openai.com/api-keys . Add `OPENAI_MODEL` = `gpt-5.5` (or another model available to your API account). Keep `ADMIN_PASSWORD` and `SESSION_SECRET` as they are. **Do not replace existing secrets with blank Blueprint values.**
4. Set `JH3_DB` aside; it is ignored when `DATABASE_URL` is set. You may remove it after confirming PostgreSQL is working.
5. Save/deploy the environment changes. In Render > Manual Deploy, deploy the latest commit if needed.
6. Sign in and visit `https://YOUR-SERVICE.onrender.com/api/system-status`. Expect `database: postgresql`, `ai: enabled`, `email_sending: disabled`.
7. Add a **fictional** test lead, generate a draft, classify a sample interested response, restart/redeploy the service and confirm the lead still exists.

## Costs and limits
Render Free may spin down. Supabase Free is subject to project limits and possible inactivity policies. OpenAI API calls are **billed separately** from ChatGPT; set API project usage limits and monitor costs. This is a controlled pilot, not a production security certification.

## Data migration
Old SQLite records do **not** automatically migrate. Export CSV from the existing dashboard **before** upgrading if you need the lead list. The CSV only includes leads, not prior replies/drafts. Existing records in Render's ephemeral SQLite may already be gone. Import the CSV into Version 3 after PostgreSQL is configured.

## Safety
Never commit secrets, database URLs, or `.env` files. Keep the GitHub repository private. Do not add actual customer data until backups, retention, and data-processing controls are reviewed. AI-generated drafts still require manual approval. The system does not independently discover real businesses, verify their email addresses, or send mail.

## Troubleshooting
- `RuntimeError` about credentials: check `ADMIN_PASSWORD` length 16+ and `SESSION_SECRET` length 32+.
- Database startup error: verify Supabase project is running, the exact session-pooler string, password URL encoding, and SSL connectivity.
- AI 503: `OPENAI_API_KEY` missing.
- AI 502: check Render logs, OpenAI API billing/model access; no draft/reply is stored on a failed AI call.
- Check `GET /health` for web process availability; it does not prove database connectivity. Use `/api/system-status` and an actual test lead for end-to-end checks.
