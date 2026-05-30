"""PhotonBox (光子盒) weekly-report auto-translator.

Discovers the latest 光子盒 周报 via Sogou WeChat Search, fetches the article,
translates it Chinese → English with Claude, and emails the result via Gmail SMTP.

Designed to run as a weekly GitHub Actions cron job. Tracks the last-seen
article URL in state.json so it never sends the same digest twice.

Required environment variables:
    ANTHROPIC_API_KEY    - Anthropic API key
    SENDER_EMAIL         - Gmail address that will send the digest
    SENDER_APP_PASSWORD  - 16-char Google App Password (2FA must be on)
    RECEIVER_EMAIL       - Inbox the digest lands in

Optional:
    STATE_FILE   - path to state JSON (default: ./state.json)
    CLAUDE_MODEL - override translation model (default: claude-sonnet-4-6)

Flags:
    --force      ignore state, re-translate even if URL already seen
    --dry-run    fetch + translate + print, but don't email or update state
"""

from __future__ import annotations

import argparse
import html
import hashlib
import json
import os
import re
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import markdown
import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup

SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
ALBUM_API_URL = "https://mp.weixin.qq.com/mp/appmsgalbum"
# 光子盒's 周报 collection. Find this by opening any weekly in WeChat → tap the
# collection link at the top → share/copy that URL; pull out __biz and album_id.
DEFAULT_ALBUM_BIZ = "MzAxMTgyMDQ2Mw=="
DEFAULT_ALBUM_ID = "1806520255742083074"
ACCOUNT_NAME = "光子盒"
KEYWORD = "周报"
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "cache"))
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_MODEL = "claude-sonnet-4-6"


def log(msg: str) -> None:
    print(f"[photonbox] {msg}", flush=True)


def unescape_html_entities(value: str, max_rounds: int = 5) -> str:
    """Decode nested HTML entities (e.g. &amp;amp; -> &amp; -> &)."""
    out = value
    for _ in range(max_rounds):
        nxt = html.unescape(out)
        if nxt == out:
            break
        out = nxt
    return out


def fetch_latest_from_album(
    biz: str = DEFAULT_ALBUM_BIZ,
    album_id: str = DEFAULT_ALBUM_ID,
    title_must_contain: str = KEYWORD,
) -> dict | None:
    """Hit the album JSON API and return the newest matching item.

    Returns {title, url, account, create_time} or None. The album endpoint is
    publicly accessible and returns reverse-chronological results.
    """
    params = {
        "__biz": biz,
        "action": "getalbum",
        "album_id": album_id,
        "count": "20",
        "is_reverse": "0",
        "f": "json",
    }
    headers = {"User-Agent": USER_AGENT, "Referer": "https://mp.weixin.qq.com/"}
    resp = requests.get(ALBUM_API_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    arts = data.get("getalbum_resp", {}).get("article_list", [])
    log(f"Album returned {len(arts)} newest items")
    for a in arts[:5]:
        log(f"  - {a.get('title', '')[:80]}")
    for a in arts:
        if title_must_contain and title_must_contain not in a.get("title", ""):
            continue
        return {
            "title": a["title"],
            "url": unescape_html_entities(a["url"]),
            "account": ACCOUNT_NAME,
            "create_time": a.get("create_time"),
        }
    return None


def search_sogou_for_latest_weekly(
    query: str = ACCOUNT_NAME, title_must_contain: str = KEYWORD
) -> dict | None:
    """Return {title, url, account} for the first matching 光子盒 article, or None.

    `query` is what gets sent to Sogou; `title_must_contain` is the post-filter
    applied to result titles (use '' to disable). The account filter (must
    contain '光子盒') always applies.
    """
    params = {"type": 2, "query": query, "ie": "utf8"}
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = requests.get(SOGOU_SEARCH_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()

    if "请输入验证码" in resp.text or "antispider" in resp.text:
        raise RuntimeError(
            "Sogou served a CAPTCHA. Try again later, rotate IPs, or wire up a "
            "Playwright fallback."
        )

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates = []
    for box in soup.select("div.txt-box"):
        title_link = box.select_one("h3 a, h4 a")
        account_link = box.select_one("a.account")
        if not title_link:
            continue
        href = title_link.get("href", "")
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin("https://weixin.sogou.com", href)
        candidates.append(
            {
                "title": title_link.get_text(strip=True),
                "sogou_url": href,
                "account": account_link.get_text(strip=True) if account_link else "",
            }
        )

    log(f"Sogou returned {len(candidates)} article candidates for query {query!r}")
    for c in candidates[:10]:
        log(f"  - [{c['account']}] {c['title']}")

    for c in candidates:
        if ACCOUNT_NAME not in c["account"]:
            continue
        if title_must_contain and title_must_contain not in c["title"]:
            continue
        real_url = resolve_sogou_redirect(c["sogou_url"], headers)
        if real_url:
            return {"title": c["title"], "url": real_url, "account": c["account"]}
        log("Matched result but could not resolve its real URL; trying next.")

    return None


def resolve_sogou_redirect(sogou_url: str, headers: dict) -> str | None:
    """Sogou's /link page returns JS that assembles the real mp.weixin.qq.com URL."""
    resp = requests.get(sogou_url, headers=headers, timeout=30, allow_redirects=False)
    location = resp.headers.get("Location", "")
    if resp.status_code in (301, 302) and "mp.weixin.qq.com" in location:
        return location

    pieces = re.findall(r"url\s*\+=\s*'([^']*)'", resp.text)
    if pieces:
        joined = "".join(pieces).replace("@", "").replace("&amp;", "&")
        if joined.startswith("http"):
            return joined

    m = re.search(r"var\s+url\s*=\s*'(https?://[^']+)'", resp.text)
    if m:
        return m.group(1).replace("&amp;", "&")

    return None


def fetch_article(url: str) -> dict:
    """Return {title, text} from a WeChat mp article URL."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title_el = soup.select_one("h1.rich_media_title, h2.rich_media_title")
    title = title_el.get_text(strip=True) if title_el else "光子盒周报"

    body = soup.select_one("#js_content, div.rich_media_content")
    if not body:
        raise RuntimeError("Could not locate article body in WeChat HTML.")

    for br in body.find_all("br"):
        br.replace_with("\n")
    text = body.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return {"title": title, "text": text}


def translate(title: str, body_text: str, model: str) -> str:
    """Stream the translation so long outputs don't hit the non-streaming timeout."""
    client = Anthropic()
    system = (
        "You translate Chinese-language quantum-computing weekly reports into clear, "
        "professional English. The audience is technical: physicists, deep-tech "
        "investors, and engineers. Preserve every section header, bullet, numbered "
        "list, company name, and source attribution. Use accurate technical "
        "terminology (量子比特 → qubit, 超导量子 → superconducting quantum, 离子阱 → "
        "ion trap, 量子优越性 → quantum advantage, 纠错 → error correction, 退相干 → "
        "decoherence, 保真度 → fidelity). Render output as clean Markdown. Translate "
        "only — no commentary, no summary, no opinions. Keep proper nouns (company, "
        "lab, and person names) in their original form, optionally with an English "
        "gloss in parentheses on first occurrence."
    )
    chunks: list[str] = []
    last_log = time.time()
    with client.messages.stream(
        model=model,
        max_tokens=32000,
        system=system,
        messages=[{"role": "user", "content": f"# {title}\n\n{body_text}"}],
    ) as stream:
        for delta in stream.text_stream:
            chunks.append(delta)
            now = time.time()
            if now - last_log >= 10:
                log(f"  ... streamed {sum(len(c) for c in chunks)} chars so far")
                last_log = now
    return "".join(chunks).strip()


def extract_english_title(translated_md: str) -> str | None:
    """First markdown heading from translated output, or None."""
    for line in translated_md.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
    return None


def _build_email_payload(subject_zh: str, translated_md: str, source_url: str) -> dict:
    """Shared HTML/text/subject construction used by all transports."""
    sender = os.environ["SENDER_EMAIL"]
    raw = os.environ["RECEIVER_EMAIL"]
    recipients = [r.strip() for r in raw.split(",") if r.strip()]
    if not recipients:
        raise RuntimeError("RECEIVER_EMAIL is empty")
    body_html = markdown.markdown(translated_md, extensions=["extra", "nl2br"])
    full_html = (
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        '<body style="font-family:-apple-system,system-ui,sans-serif;'
        'max-width:720px;margin:0 auto;padding:24px;line-height:1.6;color:#222;">'
        f'<p style="color:#666;font-size:13px;margin:0 0 8px;">'
        f'Source: <a href="{source_url}">{source_url}</a><br>'
        f'Original title: {subject_zh}</p>'
        '<hr style="border:none;border-top:1px solid #eee;margin:16px 0;">'
        f"{body_html}</body></html>"
    )
    subject_en = extract_english_title(translated_md) or subject_zh
    return {
        "sender": sender,
        "recipients": recipients,
        "subject": f"PhotonBox Quantum Weekly: {subject_en}",
        "text": translated_md,
        "html": full_html,
    }


def send_via_graph(payload: dict) -> None:
    """Send via Microsoft Graph API using client_credentials OAuth flow.

    Requires an Azure AD app registration with `Mail.Send` Application permission
    granted admin consent. Mail is signed with the M365 tenant's DKIM key, so it
    arrives properly verified regardless of source IP.
    """
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]
    sender = payload["sender"]
    recipients = payload["recipients"]

    log(f"Acquiring Graph API token (tenant {tenant_id[:8]}…)")
    tok = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    if tok.status_code >= 400:
        raise RuntimeError(f"Graph token error {tok.status_code}: {tok.text}")
    access_token = tok.json()["access_token"]

    log(f"Sending via Graph as {sender} → {', '.join(recipients)}")
    resp = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "message": {
                "subject": payload["subject"],
                "body": {"contentType": "HTML", "content": payload["html"]},
                "toRecipients": [
                    {"emailAddress": {"address": r}} for r in recipients
                ],
                "replyTo": [{"emailAddress": {"address": sender}}],
            },
            "saveToSentItems": "true",
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Graph sendMail error {resp.status_code}: {resp.text}")
    log(f"Graph API accepted (HTTP {resp.status_code})")


def send_via_mailersend(payload: dict) -> None:
    api_key = os.environ["MAILERSEND_API_KEY"]
    sender = payload["sender"]
    recipients = payload["recipients"]
    log(f"Sending via MailerSend from {sender} to {', '.join(recipients)}")
    resp = requests.post(
        "https://api.mailersend.com/v1/email",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        json={
            "from": {"email": sender, "name": "PhotonBox Weekly Digest"},
            "to": [{"email": r} for r in recipients],
            "reply_to": [{"email": sender}],
            "subject": payload["subject"],
            "html": payload["html"],
            "text": payload["text"],
            "headers": [
                {"name": "List-Id", "value": "PhotonBox Quantum Weekly <photonbox-weekly.local>"},
                {"name": "List-Unsubscribe", "value": f"<mailto:{sender}?subject=unsubscribe>"},
                {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
                {"name": "Auto-Submitted", "value": "auto-generated"},
            ],
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"MailerSend API error {resp.status_code}: {resp.text}")
    msg_id = resp.headers.get("X-Message-Id", "(no id)")
    log(f"MailerSend accepted; message id: {msg_id}")


def send_via_resend(payload: dict) -> None:
    api_key = os.environ["RESEND_API_KEY"]
    sender = payload["sender"]
    recipients = payload["recipients"]
    log(f"Sending via Resend from {sender} to {', '.join(recipients)}")
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": f"PhotonBox Weekly Digest <{sender}>",
            "to": recipients,
            "subject": payload["subject"],
            "html": payload["html"],
            "text": payload["text"],
            "reply_to": sender,
            "headers": {
                "List-Id": "PhotonBox Quantum Weekly <photonbox-weekly.local>",
                "List-Unsubscribe": f"<mailto:{sender}?subject=unsubscribe>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                "Auto-Submitted": "auto-generated",
            },
        },
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")
    log(f"Resend message id: {resp.json().get('id')}")


def send_via_smtp(payload: dict) -> None:
    from email.utils import formatdate, make_msgid

    sender = payload["sender"]
    recipients = payload["recipients"]
    password = os.environ.get("SENDER_APP_PASSWORD", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_use_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")
    smtp_username = os.environ.get("SMTP_USERNAME", sender)
    # Empty password means unauthenticated relay (e.g. M365 Direct Send).
    use_auth = bool(password)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = payload["subject"]
    msg["From"] = f"PhotonBox Weekly Digest <{sender}>"
    msg["To"] = ", ".join(recipients)
    msg["Reply-To"] = sender
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="photonbox-weekly")
    msg["List-Id"] = "PhotonBox Quantum Weekly <photonbox-weekly.local>"
    msg["List-Unsubscribe"] = f"<mailto:{sender}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg["X-Mailer"] = "photonbox_weekly.py"
    msg["Auto-Submitted"] = "auto-generated"
    msg.attach(MIMEText(payload["text"], "plain", "utf-8"))
    msg.attach(MIMEText(payload["html"], "html", "utf-8"))

    smtp_cls = smtplib.SMTP_SSL if smtp_use_ssl else smtplib.SMTP
    log(f"SMTP {smtp_host}:{smtp_port} (ssl={smtp_use_ssl}, auth={use_auth})")
    with smtp_cls(smtp_host, smtp_port) as server:
        if not smtp_use_ssl:
            # Try STARTTLS but don't fail if the server doesn't offer it
            # (M365 Direct Send on port 25 advertises STARTTLS; older relays don't).
            try:
                server.starttls()
            except smtplib.SMTPException as e:
                log(f"STARTTLS not available, continuing in plain: {e}")
        if use_auth:
            server.login(smtp_username, password)
        server.send_message(msg, from_addr=sender, to_addrs=recipients)


def send_email(subject_zh: str, translated_md: str, source_url: str) -> None:
    payload = _build_email_payload(subject_zh, translated_md, source_url)
    if os.environ.get("AZURE_CLIENT_SECRET"):
        send_via_graph(payload)
    elif os.environ.get("MAILERSEND_API_KEY"):
        send_via_mailersend(payload)
    elif os.environ.get("RESEND_API_KEY"):
        send_via_resend(payload)
    else:
        send_via_smtp(payload)
    log(f"Emailed translation to {', '.join(payload['recipients'])}")


def cache_path(url: str) -> Path:
    h = hashlib.sha256(canonicalize(url).encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def load_cached_translation(url: str) -> dict | None:
    p = cache_path(url)
    if p.exists():
        return json.loads(p.read_text())
    return None


def save_cached_translation(url: str, title_zh: str, text_zh: str, text_en: str, model: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": url,
        "title_zh": title_zh,
        "text_zh": text_zh,
        "text_en": text_en,
        "model": model,
        "translated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    p = cache_path(url)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return p


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def canonicalize(url: str) -> str:
    parts = urlsplit(unescape_html_entities(url))
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if path.startswith("/s/"):
        return f"https://{host}{path}"
    if path == "/s":
        q = parse_qs(parts.query, keep_blank_values=False)
        keep = {}
        for k in ("__biz", "mid", "idx", "sn"):
            vals = q.get(k, [])
            if len(vals) == 1 and vals[0]:
                keep[k] = vals[0]
        if keep:
            ordered = [(k, keep[k]) for k in ("__biz", "mid", "idx", "sn") if k in keep]
            return f"https://{host}{path}?{urlencode(ordered)}"
    return f"https://{host}{path}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="ignore state.json")
    parser.add_argument("--dry-run", action="store_true", help="don't email or save state")
    parser.add_argument(
        "--query",
        default=ACCOUNT_NAME,
        help="Sogou search query (default: 光子盒). Use e.g. '光子盒周报第317期' to target a specific issue.",
    )
    parser.add_argument(
        "--title-contains",
        default=KEYWORD,
        help="Substring the result title must contain (default: 周报). Pass '' to disable.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Skip Sogou search and directly translate the given mp.weixin.qq.com URL.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the translation cache (force a fresh Claude call).",
    )
    parser.add_argument(
        "--discovery",
        choices=["album", "sogou"],
        default="album",
        help="How to discover the latest weekly. 'album' (default) hits the WeChat "
        "appmsgalbum JSON API for 光子盒's 周报 collection — reliable. 'sogou' uses "
        "weixin.sogou.com — index is years stale, kept only as fallback.",
    )
    args = parser.parse_args()

    state_path = Path(os.environ.get("STATE_FILE", "state.json"))
    state = load_state(state_path)
    last_url = state.get("last_url")
    log(f"Last seen URL: {last_url or '(none)'}")

    if args.url:
        log(f"Using explicit --url: {args.url}")
        hit = {"title": "(from --url)", "url": args.url, "account": ACCOUNT_NAME}
    elif args.discovery == "album":
        log("Fetching newest 周报 from 光子盒 album API...")
        hit = fetch_latest_from_album(title_must_contain=args.title_contains)
        if not hit:
            log("No 周报 found in album. Nothing to do.")
            return 0
        log(f"Found: {hit['title']}")
        log(f"URL: {hit['url']}")
    else:
        log(f"Searching Sogou with query={args.query!r}, title_contains={args.title_contains!r}...")
        hit = search_sogou_for_latest_weekly(args.query, args.title_contains)
        if not hit:
            log("No 周报 article found from 光子盒 in Sogou results. Nothing to do.")
            return 0
        log(f"Found: [{hit['account']}] {hit['title']}")
        log(f"URL: {hit['url']}")

    if not args.force and last_url and canonicalize(hit["url"]) == canonicalize(last_url):
        log("Already translated this article. Skipping.")
        return 0

    model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    cached = None if args.no_cache else load_cached_translation(hit["url"])
    if cached:
        log(f"Using cached translation from {cached['translated_at']} (model={cached['model']})")
        article = {"title": cached["title_zh"], "text": cached["text_zh"]}
        english = cached["text_en"]
    else:
        log("Fetching article body...")
        article = fetch_article(hit["url"])
        log(f"Got {len(article['text'])} chars of Chinese text.")
        log(f"Translating with {model}...")
        english = translate(article["title"], article["text"], model)
        log(f"Translation produced {len(english)} chars.")
        path = save_cached_translation(hit["url"], article["title"], article["text"], english, model)
        log(f"Cached translation at {path}")

    if args.dry_run:
        log("--- DRY RUN OUTPUT ---")
        print(english)
        log("--- END DRY RUN ---")
        return 0

    log("Sending email...")
    send_email(article["title"], english, hit["url"])

    state["last_url"] = hit["url"]
    state["last_title"] = article["title"]
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(state_path, state)
    log("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
