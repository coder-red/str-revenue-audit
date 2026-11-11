# Deploy

**Live now (Render, free tier):**

- App: <https://str-revenue-audit.onrender.com> (sleeps when idle; first load ~30–60 s)
- Landing page: <https://str-revenue-audit-site.onrender.com>

Both auto-deploy from `main` on push (autoDeploy = yes). The app reads `GROQ_API_KEY` etc.
from Render env vars — **rotate the key that was pasted in chat** and update it in the
Render dashboard → service `str-revenue-audit` → Environment.

Alternative hosts (not used, kept for reference):

## 1. Streamlit app → Streamlit Community Cloud (free, ~3 min)

1. Go to <https://share.streamlit.io> and sign in with GitHub (account `coder-red`).
2. **Create app** → **Public GitHub repo** → `coder-red/str-revenue-audit`
3. **Branch:** `main` · **Main file path:** `app.py`
4. **Advanced settings → Secrets**, paste:
   ```toml
   LLM_PROVIDER = "groq"
   GROQ_API_KEY = "gsk_..."   # your CURRENT key (the one pasted in chat was exposed — rotate first)
   GROQ_MODEL = "openai/gpt-oss-120b"
   ```
5. **Deploy.** Your URL will be `https://<chosen-name>.streamlit.app`.

The 7 MB Austin `listings.csv.gz` is committed, so no data-download step is needed in the cloud.

## 2. Landing page → Vercel (free, ~2 min)

Option A — import from GitHub (no token needed):
1. Go to <https://vercel.com/new> → **Continue with GitHub** → import `coder-red/str-revenue-audit`
2. **Root Directory:** `site` · **Framework preset:** Other · no build command, no output dir
3. **Deploy.** Done — every push to `main` redeploys automatically.

Option B — from this machine with a token:
1. Create a token at <https://vercel.com/account/tokens>
2. `cd site && npx vercel --prod --yes --token <TOKEN>`

## Honesty notes

- Vercel **cannot** host the Streamlit app itself (no persistent processes/WebSockets).
  It hosts the static landing page; Render hosts both (this is what's live now).
- The 2026-09-17 Inside Airbnb snapshot is pinned in `str_audit/comps.py` and the PDF footer —
  refresh deliberately, not silently.
- Render free tier: 512 MB RAM, sleeps after 15 min idle, ~30–60 s cold start. Fine for a portfolio demo.
