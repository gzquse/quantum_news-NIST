"""NIST post-quantum cryptography (PQC) history map – weekly updater.

Every week this script:

1. Pulls NIST's official PQC news lists (CSRC "Post-Quantum Cryptography" news and
   the "Additional Digital Signature Schemes" news) and detects items it has not
   seen before.
2. Probes a small "watch list" of NIST publication URLs that do not exist yet
   (draft FIPS 206, FIPS 207/HQC, final IR 8547, ...) and reports the moment one
   of them goes live.
3. For each new item, fetches the NIST page, pulls out document links (PDFs,
   publication pages) and asks Claude for a short plain-English explanation.
   New items are appended to nist_pqc/updates.json so the map grows over time.
4. Renders the full history map – curated timeline (nist_pqc/timeline.json) +
   automatically discovered updates – as Markdown (NIST_PQC_HISTORY.md) and as
   an HTML email, and sends the email (default recipient: zguo@lightriderinc.com).

The email is sent every week even when nothing changed, with a clear
"What changed this week" section that says so.

Environment variables (same secrets as photonbox_weekly.py):
    ANTHROPIC_API_KEY     - Claude API key (optional in --dry-run; falls back to raw excerpt)
    SENDER_EMAIL          - From: address (noreply@lightriderinc.com)
    NIST_RECEIVER_EMAIL   - recipients, comma-separated (default: zguo@lightriderinc.com)
    AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET - Graph API send
    CLAUDE_MODEL          - override model (default: claude-sonnet-4-6)

Flags:
    --dry-run        do everything except send email / write state
    --no-email       write state + markdown, skip the email
    --force          send even if state says an email already went out this week
    --fixture-dir D  read HTML pages from D/<sha1(url)>.html instead of the network (tests)
    --record-dir D   save every fetched page into D (to build fixtures)
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

import photonbox_weekly as pb  # reuse the email transports (Graph / MailerSend / Resend / SMTP)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("NIST_DATA_DIR", BASE_DIR / "nist_pqc"))
TIMELINE_FILE = DATA_DIR / "timeline.json"
UPDATES_FILE = DATA_DIR / "updates.json"
STATE_FILE = Path(os.environ.get("NIST_STATE_FILE", DATA_DIR / "state.json"))
MARKDOWN_OUT = Path(os.environ.get("NIST_MARKDOWN_OUT", BASE_DIR / "NIST_PQC_HISTORY.md"))
DEFAULT_RECIPIENT = "zguo@lightriderinc.com"
DEFAULT_MODEL = "claude-sonnet-4-6"

NEWS_SOURCES = [
    ("NIST PQC project news", "https://csrc.nist.gov/projects/post-quantum-cryptography/news"),
    ("NIST additional-signatures news", "https://csrc.nist.gov/Projects/pqc-dig-sig/news"),
]
PROJECT_HOME = "https://csrc.nist.gov/projects/post-quantum-cryptography"

USER_AGENT = pb.USER_AGENT
DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\.?\s+(\d{1,2}),\s+(\d{4})\b"
)
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def log(msg: str) -> None:
    print(f"[nist-pqc] {msg}", flush=True)


# --------------------------------------------------------------------------- fetch

class Fetcher:
    """HTTP fetcher with optional offline fixtures (for tests) and recording."""

    def __init__(self, fixture_dir: Path | None = None, record_dir: Path | None = None):
        self.fixture_dir = fixture_dir
        self.record_dir = record_dir
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})

    @staticmethod
    def key(url: str) -> str:
        return hashlib.sha1(url.encode()).hexdigest()

    def get(self, url: str, timeout: int = 45) -> tuple[int, str]:
        """Return (status_code, text). Never raises for HTTP errors; 0 = network error."""
        if self.fixture_dir:
            p = self.fixture_dir / f"{self.key(url)}.html"
            if p.exists():
                meta = self.fixture_dir / f"{self.key(url)}.status"
                status = int(meta.read_text().strip()) if meta.exists() else 200
                return status, p.read_text(encoding="utf-8")
            return 404, ""
        try:
            resp = self.session.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException as e:
            log(f"  network error for {url}: {e}")
            return 0, ""
        text = resp.text if resp.status_code == 200 else ""
        if self.record_dir:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            (self.record_dir / f"{self.key(url)}.html").write_text(resp.text, encoding="utf-8")
            (self.record_dir / f"{self.key(url)}.status").write_text(str(resp.status_code))
        return resp.status_code, text


# --------------------------------------------------------------------------- parsing

def parse_date(text: str) -> str | None:
    """Return ISO date (YYYY-MM-DD) for the first date found in text, else None."""
    m = DATE_RE.search(text)
    if m:
        month, day, year = MONTHS[m.group(1)], int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    m = NUMERIC_DATE_RE.search(text)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def canonical_news_url(href: str, base: str) -> str:
    u = urljoin(base, href.strip())
    parts = urlsplit(u)
    return f"https://csrc.nist.gov{parts.path.rstrip('/')}".replace("/news/", "/News/", 1)


def parse_news_list(html_text: str, base_url: str) -> list[dict]:
    """Extract {title, url, date} for every CSRC news item linked on a news list page.

    Deliberately tolerant of markup changes: any anchor whose href looks like
    /News/<year>/<slug> counts as an item; the date is taken from the nearest
    ancestor block that contains a date string.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    items: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"/news/20\d\d/[^/?#]+", href, re.IGNORECASE):
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 4:
            continue
        url = canonical_news_url(href, base_url)
        # Walk up until a container mentions a date (but stop before swallowing the whole page).
        found_date = None
        node = a
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            txt = node.get_text(" ", strip=True)
            if len(txt) > 1500:
                break
            found_date = parse_date(txt)
            if found_date:
                break
        prev = items.get(url)
        if prev is None or (not prev.get("date") and found_date):
            items[url] = {"title": title, "url": url, "date": found_date}
    return sorted(items.values(), key=lambda x: x.get("date") or "0000", reverse=True)


def extract_article(html_text: str, url: str) -> dict:
    """Return {title, date, text, links} for a CSRC news/publication page."""
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    title_el = soup.select_one("h1, h2.title, .page-title")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    main = soup.select_one("main, #main, .main-content, article, .news-content, body") or soup
    text = re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True))
    found_date = parse_date(text[:2000]) or parse_date(text)
    links: list[dict] = []
    seen = set()
    for a in main.find_all("a", href=True):
        href = urljoin(url, a["href"].strip())
        label = a.get_text(" ", strip=True) or href
        low = href.lower()
        interesting = (
            low.endswith(".pdf")
            or "nvlpubs.nist.gov" in low
            or "doi.org/10.6028" in low
            or "/pubs/" in low
            or "/publications/detail/" in low
            or "/events/" in low
            or "/projects/" in low
            or "nccoe.nist.gov" in low
        )
        if not interesting or href in seen or href.rstrip("/") == url.rstrip("/"):
            continue
        if "csrc.nist.gov/projects/post-quantum-cryptography" in low and len(label) < 6:
            continue
        seen.add(href)
        links.append({"label": label[:120], "url": href})
    return {"title": title, "date": found_date, "text": text[:12000], "links": links[:12]}


# --------------------------------------------------------------------------- Claude

def raw_excerpt(item: dict, article: dict, limit: int = 600) -> str:
    """Fallback when Claude is unavailable: first sentences of the page, minus title/date noise."""
    text = article.get("text", "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = (item.get("title") or article.get("title") or "").strip()
    body = [ln for ln in lines if ln != title and ln != article.get("title") and not DATE_RE.fullmatch(ln)]
    joined = " ".join(body)
    joined = re.sub(r"\s*\|\s*", " · ", joined)
    return joined[:limit].rstrip() + ("…" if len(joined) > limit else "")


def explain_with_claude(item: dict, article: dict, model: str) -> dict:
    """Ask Claude for a plain-English explanation. Returns {summary, why_it_matters}."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("  ANTHROPIC_API_KEY not set – using a raw excerpt instead of a Claude summary")
        return {"summary": raw_excerpt(item, article), "why_it_matters": ""}
    from anthropic import Anthropic

    client = Anthropic()
    system = (
        "You explain official NIST post-quantum cryptography announcements to a smart, "
        "curious reader who is NOT a cryptographer. Use everyday language, short sentences, "
        "no jargon without a one-phrase explanation. Never invent facts, dates, or numbers "
        "that are not in the source text. Respond ONLY with JSON: "
        '{"summary": "<2-4 sentences: what NIST actually did/published>", '
        '"why_it_matters": "<1-2 sentences: what it means for the migration to quantum-safe crypto>"}'
    )
    user = (
        f"Title: {item.get('title')}\nDate: {item.get('date')}\nURL: {item.get('url')}\n\n"
        f"Page text:\n{article['text'][:9000]}"
    )
    resp = client.messages.create(model=model, max_tokens=600, system=system,
                                  messages=[{"role": "user", "content": user}])
    raw = "".join(getattr(b, "text", "") for b in resp.content).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(m.group(0) if m else raw)
        return {"summary": str(data.get("summary", "")).strip(),
                "why_it_matters": str(data.get("why_it_matters", "")).strip()}
    except (json.JSONDecodeError, AttributeError):
        return {"summary": raw[:800], "why_it_matters": ""}


# --------------------------------------------------------------------------- state

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def timeline_known_urls(timeline: dict) -> set[str]:
    urls = set()
    for ev in timeline.get("events", []):
        for ln in ev.get("links", []):
            urls.add(ln["url"].rstrip("/").lower())
    for row in timeline.get("status_board", []):
        urls.add(row["url"].rstrip("/").lower())
    return urls


# --------------------------------------------------------------------------- discovery

def discover(fetcher: Fetcher, state: dict, timeline: dict, today: date, model: str) -> tuple[list[dict], list[dict], list[str]]:
    """Return (new_news_items, new_watch_hits, problems)."""
    seen: dict = state.setdefault("seen_urls", {})
    first_run = not seen
    known = timeline_known_urls(timeline)
    problems: list[str] = []
    discovered: list[dict] = []

    for name, src in NEWS_SOURCES:
        status, text = fetcher.get(src)
        if status != 200 or not text:
            problems.append(f"Could not load {name} ({src}) – HTTP {status}.")
            continue
        items = parse_news_list(text, src)
        log(f"{name}: {len(items)} items")
        if not items:
            problems.append(f"{name} loaded but no news items were recognised – NIST may have changed the page layout.")
        for it in items:
            it["source"] = name
        discovered.extend(items)

    # De-duplicate across sources.
    by_url: dict[str, dict] = {}
    for it in discovered:
        by_url.setdefault(it["url"], it)

    new_items: list[dict] = []
    for url, it in by_url.items():
        if url in seen:
            continue
        in_timeline = url.rstrip("/").lower() in known
        item_date = it.get("date")
        old = bool(item_date) and (today - date.fromisoformat(item_date)).days > 45
        if first_run and (in_timeline or old):
            # Seed silently: already covered by the curated map, or ancient history.
            seen[url] = {"title": it["title"], "date": item_date, "first_seen": today.isoformat(), "seeded": True}
            continue
        if in_timeline:
            seen[url] = {"title": it["title"], "date": item_date, "first_seen": today.isoformat(), "seeded": True}
            continue
        new_items.append(it)

    enriched: list[dict] = []
    for it in new_items:
        log(f"NEW: {it.get('date')} – {it['title']}")
        status, page = fetcher.get(it["url"])
        article = extract_article(page, it["url"]) if status == 200 and page else {
            "title": it["title"], "date": it.get("date"), "text": "", "links": []}
        if not it.get("date") and article.get("date"):
            it["date"] = article["date"]
        try:
            expl = explain_with_claude(it, article, model) if article["text"] else {
                "summary": "NIST page could not be fetched; see the link.", "why_it_matters": ""}
        except Exception as e:  # noqa: BLE001 – never let a summary failure kill the run
            log(f"  Claude explanation failed: {e}")
            expl = {"summary": article["text"][:500], "why_it_matters": ""}
        enriched.append({
            "date": it.get("date") or today.isoformat(),
            "title": it["title"],
            "url": it["url"],
            "source": it.get("source", ""),
            "summary": expl["summary"],
            "why_it_matters": expl["why_it_matters"],
            "links": article["links"],
            "first_seen": today.isoformat(),
            "kind": "news",
        })
        seen[it["url"]] = {"title": it["title"], "date": it.get("date"), "first_seen": today.isoformat()}

    # Watch list: URLs that should not exist yet. 200 where we previously saw 404 = news.
    watch_state: dict = state.setdefault("watch", {})
    watch_hits: list[dict] = []
    for w in timeline.get("watch_list", []):
        status, page = fetcher.get(w["probe"])
        prev = watch_state.get(w["probe"], {}).get("status")
        watch_state[w["probe"]] = {"status": status, "checked": today.isoformat()}
        if status == 200 and prev != 200:
            article = extract_article(page, w["probe"])
            log(f"WATCH HIT: {w['what']} -> {w['probe']}")
            try:
                expl = explain_with_claude({"title": w["what"], "date": article.get("date"), "url": w["probe"]},
                                           article, model) if article["text"] else {"summary": "", "why_it_matters": ""}
            except Exception as e:  # noqa: BLE001
                log(f"  Claude explanation failed: {e}")
                expl = {"summary": article["text"][:500], "why_it_matters": ""}
            watch_hits.append({
                "date": article.get("date") or today.isoformat(),
                "title": f"Now live: {w['what']}" + (f" – {article['title']}" if article.get("title") else ""),
                "url": w["probe"],
                "source": "NIST publication watch list",
                "summary": expl["summary"],
                "why_it_matters": expl["why_it_matters"],
                "links": article["links"],
                "first_seen": today.isoformat(),
                "kind": "watch",
            })
        elif status == 0:
            problems.append(f"Watch probe unreachable: {w['probe']}")

    # Page-change monitor: NIST often edits key pages (e.g. a candidate withdrawn) without a
    # news post. Hash the main text of a few pages; when it changes, explain the diff.
    page_state: dict = state.setdefault("pages", {})
    for wp in timeline.get("watch_pages", []):
        status, page = fetcher.get(wp["url"])
        if status != 200 or not page:
            if status == 0:
                problems.append(f"Watch page unreachable: {wp['url']}")
            continue
        article = extract_article(page, wp["url"])
        norm = re.sub(r"\s+", " ", article["text"]).strip()
        digest = hashlib.sha256(norm.encode()).hexdigest()
        prev = page_state.get(wp["url"], {})
        page_state[wp["url"]] = {"sha256": digest, "checked": today.isoformat(), "text": norm[:15000]}
        if not prev or prev.get("sha256") == digest:
            continue
        diff = text_diff(prev.get("text", ""), norm)
        if len(diff.strip()) < 40:  # whitespace / boilerplate churn
            continue
        log(f"PAGE CHANGED: {wp['what']} -> {wp['url']}")
        try:
            expl = explain_page_change(wp, diff, model)
        except Exception as e:  # noqa: BLE001
            log(f"  Claude explanation failed: {e}")
            expl = {"summary": diff[:600], "why_it_matters": ""}
        watch_hits.append({
            "date": today.isoformat(),
            "title": f"NIST updated its page: {wp['what']}",
            "url": wp["url"],
            "source": "NIST page-change monitor",
            "summary": expl["summary"],
            "why_it_matters": expl["why_it_matters"],
            "links": [],
            "first_seen": today.isoformat(),
            "kind": "page",
        })

    return enriched, watch_hits, problems


def text_diff(old: str, new: str, limit: int = 3500) -> str:
    """Sentence-level diff of two normalised page texts; '+' added, '-' removed."""
    import difflib

    split = lambda s: [x.strip() for x in re.split(r"(?<=[.!?])\s+|\s{2,}", s) if x.strip()]  # noqa: E731
    out = []
    for line in difflib.unified_diff(split(old), split(new), lineterm="", n=0):
        if line.startswith(("+++", "---", "@@")):
            continue
        if line[:1] in "+-":
            out.append(line)
    return "\n".join(out)[:limit]


def explain_page_change(wp: dict, diff: str, model: str) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        added = [l[1:].strip() for l in diff.splitlines() if l.startswith("+")]
        removed = [l[1:].strip() for l in diff.splitlines() if l.startswith("-")]
        parts = []
        if added:
            parts.append("Added: " + " ".join(added)[:400])
        if removed:
            parts.append("Removed: " + " ".join(removed)[:300])
        return {"summary": " ".join(parts) or "Page text changed.", "why_it_matters": ""}
    from anthropic import Anthropic

    client = Anthropic()
    system = (
        "You monitor official NIST post-quantum cryptography web pages for a smart reader who is "
        "not a cryptographer. You are given a diff of the page text ('+' lines were added, '-' lines "
        "removed). Explain in plain English what actually changed and ignore cosmetic edits. Never "
        "invent facts that are not in the diff. Respond ONLY with JSON: "
        '{"summary": "<1-3 sentences: what changed>", "why_it_matters": "<0-2 sentences, or empty string>"}'
    )
    user = f"Page: {wp['what']} ({wp['url']})\n\nDiff:\n{diff}"
    resp = client.messages.create(model=model, max_tokens=400, system=system,
                                  messages=[{"role": "user", "content": user}])
    raw = "".join(getattr(b, "text", "") for b in resp.content).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(m.group(0) if m else raw)
        return {"summary": str(data.get("summary", "")).strip(),
                "why_it_matters": str(data.get("why_it_matters", "")).strip()}
    except (json.JSONDecodeError, AttributeError):
        return {"summary": raw[:600], "why_it_matters": ""}


# --------------------------------------------------------------------------- rendering

def fmt_date(iso: str | None) -> str:
    if not iso:
        return "date unknown"
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y").replace(" 0", " ")
    except ValueError:
        return iso


def live_status_board(timeline: dict, state: dict) -> list[dict]:
    """Status board rows, annotated when a watch-list URL the row names has gone live."""
    watch = state.get("watch", {})
    live = {u for u, v in watch.items() if v.get("status") == 200}
    rows = []
    for row in timeline["status_board"]:
        row = dict(row)
        hits = [w for w in timeline.get("watch_list", []) if w["probe"] in live and w.get("affects") == row.get("id")]
        if hits:
            row["status"] += " — UPDATE: " + "; ".join(f"{h['what']} is now live" for h in hits)
            row["url"] = hits[-1]["probe"]
        rows.append(row)
    return rows


def merged_events(timeline: dict, updates: list[dict]) -> list[dict]:
    """Curated events + auto-discovered updates, sorted chronologically."""
    events = []
    for ev in timeline["events"]:
        events.append({**ev, "auto": False})
    for up in updates:
        events.append({
            "date": up["date"],
            "era": "expansion" if up["date"] >= "2024-08-14" else "standards",
            "title": up["title"],
            "plain": up["summary"] + (f" Why it matters: {up['why_it_matters']}" if up.get("why_it_matters") else ""),
            "links": [{"label": "NIST announcement", "url": up["url"]}] + up.get("links", []),
            "auto": True,
            "first_seen": up.get("first_seen"),
        })
    return sorted(events, key=lambda e: e["date"])


def render_markdown(timeline: dict, updates: list[dict], this_week: list[dict], problems: list[str], today: date, state: dict | None = None) -> str:
    out: list[str] = []
    out.append(f"# NIST Post-Quantum Cryptography – History Map\n")
    out.append(f"_Auto-updated weekly. Last refresh: {fmt_date(today.isoformat())}. "
               f"Every entry links to the original NIST page and document._\n")
    why = next((e for e in timeline["eras"] if e["id"] == "why"), None)
    if why:
        out.append(f"## {why['title']}\n\n{why['plain']}\n")

    out.append("## What changed this week\n")
    if this_week:
        for up in this_week:
            out.append(f"### {fmt_date(up['date'])} – {up['title']}\n")
            out.append(f"{up['summary']}\n")
            if up.get("why_it_matters"):
                out.append(f"**Why it matters:** {up['why_it_matters']}\n")
            out.append(f"- Original: <{up['url']}>")
            for ln in up.get("links", []):
                out.append(f"- {ln['label']}: <{ln['url']}>")
            out.append("")
    else:
        last = max(merged_events(timeline, updates), key=lambda e: e["date"])
        out.append(f"No new NIST PQC announcements this week. Most recent item on record: "
                   f"**{last['title']}** ({fmt_date(last['date'])}).\n")
    if problems:
        out.append("> ⚠️ Checks that could not complete this week: " + " ".join(problems) + "\n")

    out.append("## Where things stand right now\n")
    out.append("| Item | Status | Since | Link |\n|---|---|---|---|")
    for row in live_status_board(timeline, state or {}):
        out.append(f"| {row['item']} | {row['status']} | {fmt_date(row['since'])} | [NIST]({row['url']}) |")
    out.append("")

    out.append("## The full timeline\n")
    events = merged_events(timeline, updates)
    for era in timeline["eras"]:
        if era["id"] in ("why", "next"):
            continue
        evs = [e for e in events if e["era"] == era["id"]]
        if not evs:
            continue
        out.append(f"### {era['title']}\n")
        for e in evs:
            tag = " _(auto-added)_" if e.get("auto") else ""
            out.append(f"#### {fmt_date(e['date'])} – {e['title']}{tag}\n")
            out.append(f"{e['plain']}\n")
            out.append("Links: " + " · ".join(f"[{ln['label']}]({ln['url']})" for ln in e["links"]) + "\n")

    nxt = next((e for e in timeline["eras"] if e["id"] == "next"), None)
    out.append(f"## {nxt['title'] if nxt else 'What is coming next'}\n")
    out.append("These NIST pages do not exist yet; the weekly job checks them and will flag the moment one goes live.\n")
    for w in timeline["watch_list"]:
        out.append(f"- {w['what']} – will appear at <{w['probe']}>")
    out.append("")

    out.append("## Plain-English glossary\n")
    for g in timeline["glossary"]:
        out.append(f"- **{g['term']}** – {g['plain']}")
    out.append("")
    out.append(f"---\n_Sources: NIST CSRC PQC project <{PROJECT_HOME}> and its news pages. "
               f"Generated by `nist_pqc_weekly.py`._\n")
    return "\n".join(out)


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _links_html(links: list[dict]) -> str:
    return " · ".join(f'<a href="{_esc(l["url"])}" style="color:#0b5cad;">{_esc(l["label"])}</a>' for l in links)


def render_html(timeline: dict, updates: list[dict], this_week: list[dict], problems: list[str], today: date, state: dict | None = None) -> str:
    p: list[str] = []
    p.append('<!doctype html><html><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
             '<body style="margin:0;background:#f4f6f9;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1f2933;">'
             '<div style="max-width:760px;margin:0 auto;padding:24px 16px;">')
    p.append(f'<h1 style="font-size:24px;margin:0 0 4px;">NIST Post-Quantum Cryptography – History Map</h1>'
             f'<p style="margin:0 0 20px;color:#616e7c;font-size:13px;">Weekly refresh · {_esc(fmt_date(today.isoformat()))} · '
             f'Original NIST source: <a href="{PROJECT_HOME}" style="color:#0b5cad;">csrc.nist.gov/projects/post-quantum-cryptography</a></p>')

    # What changed
    p.append('<div style="background:#fff;border:1px solid #e1e5ea;border-left:5px solid #0b5cad;border-radius:8px;padding:16px 18px;margin-bottom:18px;">')
    p.append('<h2 style="font-size:18px;margin:0 0 10px;">What changed this week</h2>')
    if this_week:
        for up in this_week:
            p.append(f'<h3 style="font-size:15px;margin:14px 0 4px;">{_esc(fmt_date(up["date"]))} – {_esc(up["title"])}</h3>')
            p.append(f'<p style="margin:0 0 6px;line-height:1.55;">{_esc(up["summary"])}</p>')
            if up.get("why_it_matters"):
                p.append(f'<p style="margin:0 0 6px;line-height:1.55;"><b>Why it matters:</b> {_esc(up["why_it_matters"])}</p>')
            links = [{"label": "Original NIST page", "url": up["url"]}] + up.get("links", [])
            p.append(f'<p style="margin:0;font-size:13px;">{_links_html(links)}</p>')
    else:
        last = max(merged_events(timeline, updates), key=lambda e: e["date"])
        p.append(f'<p style="margin:0;line-height:1.55;">No new NIST PQC announcements this week. '
                 f'Most recent item on record: <b>{_esc(last["title"])}</b> ({_esc(fmt_date(last["date"]))}).</p>')
    if problems:
        p.append('<p style="margin:10px 0 0;font-size:12px;color:#8a5a00;background:#fff7e0;padding:8px;border-radius:6px;">'
                 '⚠️ Checks that could not complete this week: ' + _esc(" ".join(problems)) + '</p>')
    p.append('</div>')

    # Why it matters
    why = next((e for e in timeline["eras"] if e["id"] == "why"), None)
    if why:
        p.append('<div style="background:#eef4fb;border-radius:8px;padding:14px 18px;margin-bottom:18px;">'
                 f'<h2 style="font-size:16px;margin:0 0 6px;">{_esc(why["title"])}</h2>'
                 f'<p style="margin:0;line-height:1.55;">{_esc(why["plain"])}</p></div>')

    # Status board
    p.append('<h2 style="font-size:18px;margin:22px 0 8px;">Where things stand right now</h2>')
    p.append('<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e1e5ea;border-radius:8px;font-size:13px;">')
    p.append('<tr style="background:#f0f3f7;"><th style="text-align:left;padding:8px;">Item</th>'
             '<th style="text-align:left;padding:8px;">Status</th><th style="text-align:left;padding:8px;">Since</th></tr>')
    for row in live_status_board(timeline, state or {}):
        final = row["status"].lower().startswith("final")
        badge_bg, badge_fg = ("#dff5e3", "#146c2e") if final else ("#fff1cc", "#7a5200")
        p.append('<tr style="border-top:1px solid #e9edf1;">'
                 f'<td style="padding:8px;"><a href="{_esc(row["url"])}" style="color:#0b5cad;">{_esc(row["item"])}</a></td>'
                 f'<td style="padding:8px;"><span style="background:{badge_bg};color:{badge_fg};padding:2px 8px;border-radius:10px;">{_esc(row["status"])}</span></td>'
                 f'<td style="padding:8px;white-space:nowrap;">{_esc(fmt_date(row["since"]))}</td></tr>')
    p.append('</table>')

    # Timeline
    p.append('<h2 style="font-size:18px;margin:26px 0 8px;">The full timeline</h2>')
    events = merged_events(timeline, updates)
    for era in timeline["eras"]:
        if era["id"] in ("why", "next"):
            continue
        evs = [e for e in events if e["era"] == era["id"]]
        if not evs:
            continue
        p.append(f'<h3 style="font-size:14px;margin:18px 0 8px;color:#616e7c;text-transform:uppercase;letter-spacing:.04em;">{_esc(era["title"])}</h3>')
        p.append('<div style="border-left:3px solid #c7d2de;margin-left:6px;padding-left:16px;">')
        for e in evs:
            dot = "#0b5cad" if not e.get("auto") else "#c2410c"
            tag = ' <span style="font-size:11px;color:#c2410c;">auto-added</span>' if e.get("auto") else ""
            p.append('<div style="position:relative;margin:0 0 14px;background:#fff;border:1px solid #e1e5ea;border-radius:8px;padding:10px 14px;">'
                     f'<div style="position:absolute;left:-25px;top:14px;width:11px;height:11px;border-radius:50%;background:{dot};border:2px solid #f4f6f9;"></div>'
                     f'<div style="font-size:12px;color:#616e7c;">{_esc(fmt_date(e["date"]))}{tag}</div>'
                     f'<div style="font-weight:600;margin:2px 0 4px;">{_esc(e["title"])}</div>'
                     f'<div style="line-height:1.5;font-size:14px;">{_esc(e["plain"])}</div>'
                     f'<div style="font-size:12px;margin-top:6px;">{_links_html(e["links"])}</div></div>')
        p.append('</div>')

    # Watch list
    nxt = next((e for e in timeline["eras"] if e["id"] == "next"), None)
    p.append(f'<h2 style="font-size:18px;margin:26px 0 8px;">{_esc(nxt["title"] if nxt else "What is coming next")}</h2>')
    p.append('<p style="font-size:13px;color:#616e7c;margin:0 0 8px;">These NIST pages do not exist yet. This job checks them every week and will flag the moment one goes live.</p><ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.6;">')
    for w in timeline["watch_list"]:
        p.append(f'<li>{_esc(w["what"])} <span style="color:#9aa5b1;font-size:12px;">({_esc(w["probe"])})</span></li>')
    p.append('</ul>')

    # Glossary
    p.append('<h2 style="font-size:18px;margin:26px 0 8px;">Plain-English glossary</h2><dl style="margin:0;font-size:14px;line-height:1.5;">')
    for g in timeline["glossary"]:
        p.append(f'<dt style="font-weight:600;margin-top:8px;">{_esc(g["term"])}</dt><dd style="margin:0;">{_esc(g["plain"])}</dd>')
    p.append('</dl>')

    p.append('<p style="margin:28px 0 0;font-size:12px;color:#9aa5b1;">Generated by nist_pqc_weekly.py from the quantum_news-NIST repo. '
             'Facts and dates come from NIST\'s own pages; summaries of new items are drafted by Claude and link back to the source.</p>')
    p.append('</div></body></html>')
    return "".join(p)


# --------------------------------------------------------------------------- email

def send_email(subject: str, text_md: str, html_body: str) -> list[str]:
    sender = os.environ["SENDER_EMAIL"]
    raw = os.environ.get("NIST_RECEIVER_EMAIL") or DEFAULT_RECIPIENT
    recipients = [r.strip() for r in raw.split(",") if r.strip()]
    payload = {"sender": sender, "recipients": recipients, "subject": subject, "text": text_md, "html": html_body}
    if os.environ.get("AZURE_CLIENT_SECRET"):
        pb.send_via_graph(payload)
    elif os.environ.get("MAILERSEND_API_KEY"):
        pb.send_via_mailersend(payload)
    elif os.environ.get("RESEND_API_KEY"):
        pb.send_via_resend(payload)
    else:
        pb.send_via_smtp(payload)
    return recipients


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="no email, no state/markdown writes")
    ap.add_argument("--no-email", action="store_true", help="update state + markdown but do not send")
    ap.add_argument("--force", action="store_true", help="send even if already sent this week")
    ap.add_argument("--fixture-dir", type=Path, default=None, help="offline HTML fixtures (tests)")
    ap.add_argument("--record-dir", type=Path, default=None, help="record fetched pages here")
    ap.add_argument("--html-out", type=Path, default=None, help="also write the email HTML to this path")
    ap.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD) for tests")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    timeline = load_json(TIMELINE_FILE, None)
    if not timeline:
        log(f"Missing {TIMELINE_FILE}; nothing to do.")
        return 1
    updates: list[dict] = load_json(UPDATES_FILE, [])
    state: dict = load_json(STATE_FILE, {})

    iso_week = f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"
    if state.get("last_sent_week") == iso_week and not args.force and not args.dry_run:
        log(f"Already sent for {iso_week}; use --force to resend.")
        return 0

    fetcher = Fetcher(args.fixture_dir, args.record_dir)
    log(f"Checking NIST sources ({today.isoformat()})...")
    new_news, watch_hits, problems = discover(fetcher, state, timeline, today, model)
    # A watch-list hit that a new NIST news item already links to is the same story – keep one.
    linked = {ln["url"].rstrip("/").lower() for it in new_news for ln in it.get("links", [])}
    watch_hits = [w for w in watch_hits if w["url"].rstrip("/").lower() not in linked]
    this_week = sorted(new_news + watch_hits, key=lambda u: u["date"], reverse=True)
    log(f"{len(this_week)} new item(s); {len(problems)} problem(s)")

    known_urls = {u["url"] for u in updates}
    for up in this_week:
        if up["url"] not in known_urls:
            updates.append(up)
    updates.sort(key=lambda u: u["date"])

    md = render_markdown(timeline, updates, this_week, problems, today, state)
    html_body = render_html(timeline, updates, this_week, problems, today, state)
    n = len(this_week)
    subject = (f"NIST PQC history map – {n} new update{'s' if n != 1 else ''} · week of {fmt_date(today.isoformat())}"
               if n else f"NIST PQC history map – no NIST changes · week of {fmt_date(today.isoformat())}")

    if args.html_out:
        args.html_out.parent.mkdir(parents=True, exist_ok=True)
        args.html_out.write_text(html_body, encoding="utf-8")
        log(f"Wrote HTML preview to {args.html_out}")

    if args.dry_run:
        log("--- DRY RUN: markdown output follows ---")
        print(md)
        log(f"Subject would be: {subject}")
        return 0

    MARKDOWN_OUT.write_text(md, encoding="utf-8")
    save_json(UPDATES_FILE, updates)
    log(f"Wrote {MARKDOWN_OUT} and {UPDATES_FILE}")

    if not args.no_email:
        recipients = send_email(subject, md, html_body)
        log(f"Emailed to {', '.join(recipients)}")
        state["last_sent_week"] = iso_week
        state["last_sent"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_json(STATE_FILE, state)
    log("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
