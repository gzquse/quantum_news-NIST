# PhotonBox Weekly Translator

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

## Schedule

- **Cron**: every Saturday AND Sunday at 13:00 UTC (21:00 China time, 06:00 US Pacific).
  光子盒 publishes at ~10:55 UTC, typically Saturday but occasionally Sunday or Friday;
  firing both days catches either with a 2h buffer. `state.json` dedup ensures the
  second firing exits early if the first already sent.
- **Manual trigger**: `gh workflow run weekly.yml -f force=true` or via the GitHub UI's
  "Run workflow" button. The `force` input bypasses `state.json` dedup; default is
  `true` so manual triggers always send. Scheduled cron runs do not pass `force`,
  so they always respect dedup.

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
