#!/usr/bin/env python3
"""Generate `data/news.json` from Japanese-focused RSS sources.

Inputs:
- RSS/Atom/RDF feeds (Zenn, Qiita, JPCERT, IPA, Techracho)
- Existing `data/news.json` for merge/dedupe

Outputs:
- `data/news.json` with normalized items
- `score` supplemented by Hatena bookmark counts when available
"""

import hashlib
import json
import time
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path("data/news.json")
ARCHIVE_INDEX_PATH = Path("data/archive/index.json")
MAX_ITEMS_PER_SOURCE = 25
MAX_TOTAL_ITEMS = 500
TIMEOUT = 15

DEFAULT_HEADER = {"User-Agent": "tech-feeds-bot/1.0"}

def now():
    return datetime.now(timezone.utc).isoformat()

def safe_get(url, headers=None, params=None, retries=2):
    for attempt in range(retries + 1):
        try:
            response = requests.get(
                url,
                headers=headers or DEFAULT_HEADER,
                params=params,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response
        except Exception as error:
            if attempt == retries:
                print(f"  [WARN] {url[:60]}: {error}")
            else:
                time.sleep(1)
    return None

def load_existing():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            pass
    return {"items": [], "updated_at": ""}


def enrich_hatena_counts(items, chunk_size=50):
    """Hatena Bookmark 件数をまとめて取得して score に反映する。"""
    url_to_items = {}
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        url_to_items.setdefault(url, []).append(item)

    if not url_to_items:
        return

    urls = list(url_to_items.keys())
    total_scored = 0
    for i in range(0, len(urls), chunk_size):
        chunk = urls[i:i + chunk_size]
        params = [("url", u) for u in chunk]
        try:
            response = requests.get(
                "https://bookmark.hatenaapis.com/count/entries",
                params=params,
                headers=DEFAULT_HEADER,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            counts = response.json() if response.text else {}
        except Exception as e:
            print(f"  [WARN] Hatena count fetch failed: {e}")
            continue

        for url in chunk:
            count = int(counts.get(url, 0) or 0)
            for item in url_to_items.get(url, []):
                item["hatena_count"] = count
                # 既存 score が無い（または0）の場合は Hatena 件数で補完
                if not item.get("score"):
                    item["score"] = count
                if count > 0:
                    total_scored += 1

    print(f"[Hatena] scored_urls={total_scored}")


def parse_feed_entries(url, limit=MAX_ITEMS_PER_SOURCE):
    response = safe_get(url)
    if not response:
        return []
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        try:
            root = ET.fromstring(response.text.encode("utf-8"))
        except Exception:
            return []

    entries = []
    atom_ns = {"a": "http://www.w3.org/2005/Atom"}
    tag_name = root.tag.rsplit('}', 1)[-1] if '}' in root.tag else root.tag

    if tag_name == "feed":
        for entry in root.findall("a:entry", atom_ns):
            link = None
            for link_el in entry.findall("a:link", atom_ns):
                if link_el.get("href"):
                    link = link_el.get("href")
                    break
            title = (entry.findtext("a:title", default="", namespaces=atom_ns) or "").strip()
            published = entry.findtext("a:published", default="", namespaces=atom_ns) or entry.findtext("a:updated", default="", namespaces=atom_ns) or now()
            if title and link:
                entries.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "id": link,
                })
    else:
        # RSS 2.0 と RDF (RSS 1.0) の両方を扱う
        for item in root.findall(".//{*}item") + root.findall(".//item"):
            values = {}
            for child in list(item):
                tag = child.tag.rsplit("}", 1)[-1] if "}" in child.tag else child.tag
                values[tag] = (child.text or "").strip()
            title = values.get("title", "")
            link = values.get("link", "")
            published = values.get("pubDate") or values.get("date") or values.get("published") or now()
            if title and link:
                entries.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "id": link,
                })

    dedup = {}
    for entry in entries:
        link = entry.get("link", "")
        if link and link not in dedup:
            dedup[link] = entry

    return list(dedup.values())[:limit]

SEVERITY_KEYWORDS = {
    'critical': ['rce','remote code execution','critical','zero-day','0day','ransomware','緊急'],
    'high':     ['exploit','vulnerability','cve','privilege escalation','bypass','脆弱性'],
    'medium':   ['patch','update','advisory','warning','threat','malware','phishing'],
}
def classify_sev(title, tags, source):
    if source == 'jpcert':
        t = title.lower()
        if any(k in t for k in SEVERITY_KEYWORDS['critical']): return 'critical'
        return 'high' if 'アラート' in ' '.join(tags) or '脆弱' in title else 'info'
    t = (title+' '+' '.join(tags)).lower()
    for sev, kws in SEVERITY_KEYWORDS.items():
        if any(k in t for k in kws): return sev
    return None

def fetch_zenn():
    print("[Zenn] Fetching...")
    result = []
    for e in parse_feed_entries("https://zenn.dev/feed", MAX_ITEMS_PER_SOURCE):
        url = e.get("link", "")
        result.append({
            "id":f"zenn-{hashlib.md5(url.encode()).hexdigest()[:10]}",
            "source":"sns", "sub_source":"Zenn",
            "title":e.get("title",""), "url":url,
            "score":None, "author":"Zenn",
            "tags":["Zenn"], "date":e.get("published", now()),
        })
    print(f"  → {len(result)}")
    return result

def fetch_qiita():
    print("[Qiita] Fetching...")
    result = []
    for e in parse_feed_entries("https://qiita.com/popular-items/feed.atom", MAX_ITEMS_PER_SOURCE):
        url = e.get("link", "")
        result.append({
            "id":f"qiita-{hashlib.md5(url.encode()).hexdigest()[:10]}",
            "source":"sns", "sub_source":"Qiita",
            "title":e.get("title",""), "url":url,
            "score":None, "author":"Qiita",
            "tags":["Qiita"], "date":e.get("published", now()),
        })
    print(f"  → {len(result)}")
    return result

def fetch_jpcert():
    print("[JPCERT] Fetching...")
    items = []
    feed_url = "https://www.jpcert.or.jp/rss/jpcert.rdf"
    try:
        for e in parse_feed_entries(feed_url, 30):
            title = e.get("title", "").strip()
            sev = "high" if ("注意喚起" in title or "Alert" in title) else "info"
            items.append({
                "id": f"jpcert-{hashlib.md5(e['link'].encode()).hexdigest()[:10]}",
                "source": "jpcert",
                "title": title,
                "url": e.get("link", "").strip(),
                "score": None,
                "author": "JPCERT/CC",
                "tags": ["JPCERT", "セキュリティ"],
                "severity": sev,
                "date": e.get("published", now()),
            })
    except Exception as ex:
        print(f"  [WARN] {feed_url}: {ex}")
    print(f"  → {len(items)}")
    return items


def fetch_ipa():
    print("[IPA] Fetching...")
    items = []
    feed_url = "https://www.ipa.go.jp/security/rss/alert.rdf"
    try:
        for e in parse_feed_entries(feed_url, 20):
            items.append({
                "id": f"ipa-{hashlib.md5(e['link'].encode()).hexdigest()[:10]}",
                "source": "ipa",
                "title": e.get("title", "").strip(),
                "url": e.get("link", "").strip(),
                "score": None,
                "author": "IPA",
                "tags": ["IPA", "セキュリティ"],
                "severity": "medium",
                "date": e.get("published", now()),
            })
    except Exception as ex:
        print(f"  [WARN] {feed_url}: {ex}")
    print(f"  → {len(items)}")
    return items

def fetch_techracho():
    print("[Techracho] Fetching...")
    result = []
    for e in parse_feed_entries("https://techracho.bpsinc.jp/category/ruby-rails-related/feed", MAX_ITEMS_PER_SOURCE):
        url = e.get("link", "")
        result.append({
            "id": f"techracho-{hashlib.md5(url.encode()).hexdigest()[:10]}",
            "source": "techracho",
            "title": e.get("title", ""),
            "url": url,
            "score": None,
            "author": "Techracho",
            "tags": ["Ruby", "Rails", "日本語"],
            "date": e.get("published", now()),
        })
    print(f"  → {len(result)}")
    return result

def main():
    print(f"\n=== Fetch @ {now()} ===\n")
    existing = load_existing()

    fetchers = [fetch_zenn, fetch_qiita, fetch_jpcert, fetch_ipa, fetch_techracho]
    new_items = []
    for fetcher in fetchers:
        try:
            new_items.extend(fetcher())
        except Exception as error:
            print(f"  [ERROR] {fetcher.__name__}: {error}")

    def dedupe_key(item):
        url = str(item.get("url", "")).strip().lower()
        if url.endswith("/"):
            url = url[:-1]
        return url or str(item.get("id", ""))

    seen_keys = set()
    merged = []
    for item in new_items:
        key = dedupe_key(item)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        if "severity" not in item:
            sev = classify_sev(item.get("title",""), item.get("tags",[]), item.get("source",""))
            if sev: item["severity"] = sev
        merged.append(item)

    def is_legacy_english_item(item):
        source = str(item.get("source", "")).lower()
        url = str(item.get("url", "")).lower()
        if source in {"hn", "github", "devto", "project"} and "github.com/trending" not in url:
            return True
        english_markers = (
            "news.ycombinator.com",
            "techcrunch.com",
            "theverge.com",
            "wired.com",
            "arstechnica.com",
            "krebsonsecurity.com",
            "bleepingcomputer.com",
            "darkreading.com",
            "securityweek.com",
            "threatpost.com",
            "nvd.nist.gov",
            "exploit-db.com",
            "offsec.com",
            "portswigger.net",
            "pentest.blog",
            "dev.to",
            "technologyreview.com",
            "venturebeat.com",
            "artificialintelligence-news.com",
        )
        return any(marker in url for marker in english_markers)

    for item in existing.get("items",[]):
        if is_legacy_english_item(item):
            continue
        key = dedupe_key(item)
        if not key or key in seen_keys:
            continue
        if len(merged) < MAX_TOTAL_ITEMS:
            seen_keys.add(key)
            merged.append(item)

    enrich_hatena_counts(merged)

    def parse_datetime_safe(item):
        try:
            return datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)

    merged.sort(key=parse_datetime_safe, reverse=True)

    output = {"updated_at":now(), "count":len(merged), "items":merged}
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    if not ARCHIVE_INDEX_PATH.exists():
        print("[INFO] Monthly archive is not generated yet. Run: python scripts/gen_archive.py")
    print(f"\n=== Done: {len(merged)} items ===\n")

if __name__ == "__main__":
    main()
