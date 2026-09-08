# PhotonBox Weekly Translator + NIST PQC History Map

Two independent weekly GitHub Actions jobs live in this repo:

1. **PhotonBox Weekly Translator** (below) – translates the 光子盒 Chinese quantum weekly and emails it.
2. **[NIST PQC History Map](#nist-pqc-history-map-weekly)** – a plain-English, link-rich timeline of NIST's
   post-quantum cryptography standardisation, refreshed and emailed every Monday. See
   [`NIST_PQC_HISTORY.md`](NIST_PQC_HISTORY.md) for the current map.

---

## PhotonBox Weekly Translator

Auto-translates the [光子盒](https://mp.weixin.qq.com/) (PhotonBox) Chinese quantum-computing
weekly report into English and emails it to a list of recipients. Runs on a GitHub Actions
cron every Saturday afternoon (China time) — no servers to maintain, no manual steps.

## Pipeline

1. **Discover** the newest 光子盒 周报 by hitting the public WeChat *appmsgalbum* JSON API
   (`mp.weixin.qq.com/mp/appmsgalbum?action=getalbum&...`).
2. **Fetch** the article HTML (`mp.weixin.qq.com/s?...`) and extract the body text.
3. **Translate** Chinese → English with Claude Sonnet 4.6 via streaming, preserving
   markdown structure (headers, bullets, source links). Output is cached in
   `cache/<sha256-hex>.json` so the same article is never re-translated.
4. **Email** the translation through Microsoft Graph API as `noreply@lightriderinc.com`.
   Mail is DKIM-signed by the M365 tenant — arrives in Inbox without an "unverified" tag.
5. **Record** the sent URL in `state.json` so the next cron firing skips already-sent
   articles. The workflow commits `state.json` and `cache/` back to the repo so dedup
   and translations persist across runs.

## Files

| Path | Purpose |
|---|---|
| `photonbox_weekly.py` | The whole pipeline. Discovery, fetch, translate, send, state. |
| `.github/workflows/weekly.yml` | GitHub Actions cron + workflow_dispatch entry point. |
| `requirements.txt` | Python deps: `anthropic`, `beautifulsoup4`, `markdown`, `requests`. |
| `cache/` | One JSON per translated article (Chinese source + English output + metadata). |
| `state.json` | Last-sent URL + title + timestamp; used for dedup. |
| `.env.example` | Template for local development; real values go in `.env` (gitignored). |
| `run_weekly.sh` | Wrapper for local manual runs (sources `.env`, invokes the script). |
| `nist_pqc_weekly.py` | NIST PQC history-map job (see below). |
| `nist_pqc/timeline.json` | Hand-curated NIST PQC timeline, status board, watch list, glossary. |
| `nist_pqc/updates.json` | NIST items discovered automatically by the weekly job (grows over time). |
| `nist_pqc/state.json` | Seen URLs, watch-list HTTP status, page hashes, last-sent week. |
| `NIST_PQC_HISTORY.md` | Rendered map – regenerated and committed weekly. |
| `.github/workflows/nist_weekly.yml` | Monday cron + manual trigger for the NIST job. |

## Schedule

- **Cron**: every Saturday AND Sunday at 13:00 UTC (21:00 China time, 06:00 US Pacific).
  光子盒 publishes at ~10:55 UTC, typically Saturday but occasionally Sunday or Friday;
  firing both days catches either with a 2h buffer. `state.json` dedup ensures the
  second firing exits early if the first already sent.
- **Manual trigger**: `gh workflow run weekly.yml -f force=true` or via the GitHub UI's
  "Run workflow" button. Manual runs send with `--force` unless you explicitly set
  `force=false`, so they bypass `state.json` dedup by default. Scheduled cron runs
  do not pass `force`, so they always respect dedup.

## Required secrets

Configured under repo Settings → Secrets and variables → Actions:

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API token for translation. |
| `SENDER_EMAIL` | `noreply@lightriderinc.com`. The From: address. |
| `RECEIVER_EMAIL` | Comma-separated list of recipients. |
| `AZURE_TENANT_ID` | M365 tenant UUID. |
| `AZURE_CLIENT_ID` | Azure AD app (registered as "photon box weekly") client UUID. |
| `AZURE_CLIENT_SECRET` | Client secret value for the app. Expires; rotate as needed. |

## Email delivery (Microsoft Graph API)

Mail is sent via `POST https://graph.microsoft.com/v1.0/users/<sender>/sendMail` using
the `client_credentials` OAuth flow. The Azure AD app needs:

- **API permission**: `Mail.Send` (Application — *not* Delegated), with admin consent granted.
- Optionally: an Exchange Online `New-ApplicationAccessPolicy` restricting the app to
  only `noreply@lightriderinc.com` (otherwise the app can send as any tenant mailbox).

This path is preferred because:

- Mail is DKIM-signed by the tenant; recipients see no "unverified" warning.
- Works from any IP — no SPF/IP-allowlist concerns.
- Bypasses Microsoft 365 Security Defaults (which blocks basic SMTP AUTH).
- Compatible with GitHub Actions runners (port 25 blocked there; HTTPS is fine).

## Local development

```bash
git clone https://github.com/gzquse/photonbox-weekly.git
cd photonbox-weekly
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in real values
set -a; source .env; set +a

# Dry-run: fetch + translate + print, no email or state write
python photonbox_weekly.py --dry-run

# Real send
python photonbox_weekly.py

# Re-send the latest even if state.json says it was already sent
python photonbox_weekly.py --force

# Translate a specific article URL instead of the album's latest
python photonbox_weekly.py --url 'http://mp.weixin.qq.com/s?...'
```

## Architecture decisions

- **Discovery via the WeChat album API**, not Sogou search. Sogou's WeChat index for
  光子盒 is years stale (frozen at September 2022 as of this writing), so it was unusable.
  The album endpoint returns reverse-chronological results from the canonical source.

- **Claude API uses streaming**. Non-streaming `messages.create()` timed out at ~10 min on
  long inputs; streaming handles the typical 30K-char → 80K-char expansion cleanly.

- **`max_tokens=32000`**. A typical weekly's English translation runs ~80K chars
  (~25K tokens); 16000 was found to truncate mid-sentence.

- **Cache key = sha256-hex prefix of canonicalized URL**. Stores Chinese + English +
  model + timestamp. Always checked before invoking Claude.

- **State dedup is a single most-recent URL**, not a set. Weekly cadence + cache means
  this is enough.

## Operational notes

- Client secret expiration: when the Azure client secret expires, mail will start
  failing with HTTP 401 from Graph. Regenerate the secret in the Azure portal and
  update the `AZURE_CLIENT_SECRET` repo secret. Set a calendar reminder for the
  expiration date.
- If 光子盒 ever rotates the WeChat album, find a new weekly article in WeChat → tap the
  collection link at the top → copy the URL → extract `__biz` and `album_id` from it
  and update the constants at the top of `photonbox_weekly.py`.
- The workflow commits to `main` via `github-actions[bot]`. If you protect `main`,
  add an exception or route the commit elsewhere.

---

## NIST PQC History Map (weekly)

`nist_pqc_weekly.py` keeps a layman-friendly history of NIST's post-quantum cryptography
(PQC) work – from the 2015 workshop and the 2016 call for proposals through FIPS 203/204/205,
HQC, the transition draft (IR 8547), SP 800-227/230 and the additional-signatures rounds – and
emails it **every Monday to Martin (`zguo@`) and Anthony (`alawrence@lightriderinc.com`)**
(recipients come from the `NIST_RECEIVER_EMAIL` secret, defaulting to those two when unset).

### What the job does each week

1. **Pull NIST news.** Parses the official CSRC news lists for the
   [PQC project](https://csrc.nist.gov/projects/post-quantum-cryptography/news) and the
   [additional signatures track](https://csrc.nist.gov/Projects/pqc-dig-sig/news). Anything not
   in `nist_pqc/state.json` is new. Parsing is deliberately tolerant (any `/News/<year>/…` link
   plus the nearest date string) so small NIST layout changes don't break it; if a page yields
   zero items the email carries a ⚠️ warning instead of silently reporting "no news".
2. **Probe the watch list.** URLs that *should not exist yet* (draft/final FIPS 206, FIPS 207
   for HQC, final IR 8547, final SP 800-230/133r3, the 2027 conference). A flip from 404 → 200
   is reported as "Now live: …" and annotates the status board.
3. **Detect silent page edits.** Hashes the main text of the PQC home page, the selected-
   algorithms table, the Round 3 candidates page and the timeline page. When one changes, a
   sentence-level diff is summarised (this is how e.g. HAWK's withdrawal shows up – NIST edited
   the page without a news post).
4. **Explain in plain English.** For each new item the NIST page is fetched, document links
   (PDFs, publication pages) are extracted, and Claude writes a 2–4 sentence layman summary plus
   "why it matters". Facts come only from the NIST page text; the original link is always shown.
   New items are appended to `nist_pqc/updates.json`, so the map grows over time.
5. **Render + send.** Curated timeline + auto-discovered updates → `NIST_PQC_HISTORY.md`
   (committed) and an HTML email with: *What changed this week* (or an explicit "no NIST
   changes"), *Where things stand* status board, the full timeline, *What's coming next*, and a
   glossary. The email goes out every week even when nothing changed. `last_sent_week` in the
   state prevents double-sends within one ISO week.

### Editing the map by hand

Everything curated lives in `nist_pqc/timeline.json`:

- `events[]` – `{date, era, title, plain, links[]}`. `era` is one of the ids in `eras[]`.
- `status_board[]` – one row per standard/document; `id` lets watch-list hits annotate it.
- `watch_list[]` – `{what, probe, affects}`; `probe` is the URL that will exist one day.
- `watch_pages[]` – pages whose text is hashed for silent-edit detection.
- `glossary[]` – plain-English terms.

Auto-discovered items are in `nist_pqc/updates.json`; delete an entry there (and its URL from
`state.json → seen_urls`) to make the job re-discover and re-summarise it.

### Running locally

```bash
set -a; source .env; set +a
python nist_pqc_weekly.py --dry-run --html-out /tmp/nist.html   # no email, no writes
python nist_pqc_weekly.py --no-email                            # update md/state only
python nist_pqc_weekly.py --force                               # send now
python nist_pqc_weekly.py --record-dir tests/fixtures           # snapshot live pages
python nist_pqc_weekly.py --fixture-dir tests/fixtures --dry-run --today 2026-09-08  # offline
```

Without `ANTHROPIC_API_KEY` the job still works – new items get a raw excerpt instead of a
Claude summary.

### Schedule & secrets

- Cron `0 13 * * 1` (Monday 13:00 UTC / 09:00 US Eastern). Manual runs default to `--force`;
  tick *dry_run* to preview without emailing or committing. The rendered email is always
  uploaded as a workflow artifact (`nist-pqc-email-preview`).
- Reuses `ANTHROPIC_API_KEY`, `SENDER_EMAIL`, `AZURE_*` from the PhotonBox job. Optional:
  `NIST_RECEIVER_EMAIL` (comma-separated) – leave unset to send to zguo@ and alawrence@lightriderinc.com.
- Both workflows commit to `main`. They run on different days, and the NIST job does
  `git pull --rebase` before pushing, so they never clobber each other's commits.
