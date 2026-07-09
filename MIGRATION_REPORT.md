# MIGRATION_REPORT.md

## Deployment instructions

1. **Set the Netlify environment variable** (Site settings → Environment
   variables, or `netlify env:set`):
   ```
   MASSIVE_API_KEY=<your real Massive key>
   ```
   Never place this in `index.html`, any JS file, or a committed `.env`.

2. **Deploy the repo as-is.** `netlify.toml` already points `functions` at
   `netlify/functions` and serves `index.html` from the repo root.
   ```
   netlify deploy --prod
   ```
   or connect the repo to Netlify's Git integration for auto-deploys.

3. **Verify post-deploy**:
   - `GET https://<your-site>/.netlify/functions/health` → should return
     `{"massiveKeyConfigured": true, ...}` with no key value present.
   - Open the app, log in, open a ticker's Deck view, and confirm the
     "TOF GAMMA SPINE" panel shows `OCM: LIVE` (or a specific error) within
     ~60 seconds — this proves the full pipeline (browser → Netlify
     function → Massive → OCM engine → Gamma Spine → UI) end to end.

## Local development

```
netlify dev
```
uses `.env` (copy from `.env.example`, fill in a real key, keep it
git-ignored) to run the functions locally alongside the static `index.html`.

## What changed vs. the prior deployed file

See `INTEGRATION_REPORT.md` for the full section-by-section list. In brief:
4 client-side Massive fetch functions were repointed at same-origin
`/.netlify/functions/equity-snapshot`; the API key entry UI and its
localStorage persistence were removed; a live OCM Gamma ingestion path was
added to the Deck view; `GAMMA_MODE` (default `SHADOW`) was added; the
scanner's inaccurate "S&P stocks" label was corrected. Everything else —
scanner logic, RVOL ranking, B2O/S2O/ADD/TP/S2C/B2C signal logic, Five
Legends, sessions, paper ledger, watchlists, dark mode, mobile layout — is
byte-identical to the prior file except for the specific lines listed in
INTEGRATION_REPORT.md.

## Rollback instructions

If anything goes wrong post-deploy:

1. **Fastest rollback**: in Netlify's dashboard, go to Deploys → find the
   previous deploy → "Publish deploy". This reverts to the prior
   `index.html` (with the browser-side key) immediately. Note: that prior
   version still requires the user's browser to have a `polygonKey` set in
   localStorage from before — if they cleared storage, they'd need to
   re-enter it, since that version's `PolygonKeyField` UI is what wrote it.

2. **Partial rollback (keep security fix, drop Gamma Shadow features)**:
   set `GAMMA_MODE` to `"OFF"` via the Account screen (once exposed in UI)
   or by clearing `localStorage["cts-v1-gamma-mode"]` — this stops Gamma
   fetching/display entirely while keeping the secure transport migration
   in place. The legacy engine is completely unaffected either way, so this
   is always safe to do without touching trading behavior.

3. **Full rollback of the backend**: simply stop deploying the
   `netlify/functions/` directory (or delete the Netlify site's functions)
   — since the frontend fetch functions now point at
   `/.netlify/functions/*`, without those functions deployed those calls
   will 404 and equity/options data will stop loading. This is a hard
   rollback and would break the app's ability to show live prices at all —
   only use this if you're reverting to the old `index.html` in the same
   step (step 1 above).

## Storage compatibility

No existing localStorage keys were deleted. `cts-v1-polygon-key` (if
present from a prior session) is simply never read anymore — it's inert,
not wiped. All other `cts-v1-*` keys (risk profile, paper account, ledger,
sessions, exec state, diagnostics toggle, parity audit toggle, gamma
snapshots) continue to work exactly as before, with two new keys added
(`cts-v1-gamma-mode`, and the previously-unmapped `cts-v1-gamma-snapshots`
key was formalized into the migration map — it was already being used via
an unmapped fallback path, so no data loss occurs from this cleanup).
