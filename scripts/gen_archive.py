#!/usr/bin/env python3
"""Monthly archive generator.

Reads `data/news.json` and builds the monthly archive JSON/HTML outputs.
This version avoids external dependencies so it works in the repository environment
without installing `python-dateutil`.
"""

import gzip
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DATA_DIR = REPO_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

COMPRESS_MONTHS_AGO = 3


def parse_datetime_safe(value):
    if value is None or str(value).strip() == "":
        return datetime.now(timezone.utc)

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return datetime.now(timezone.utc)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_detail(summary, max_sentences=3):
    if not summary:
        return ""

    text = re.sub(r"\s+", " ", str(summary)).strip()
    if not text:
        return ""

    sentences = re.split(r"(?<=[。.!?])\s+", text)
    selected = []
    total_len = 0
    for sentence in sentences[:max_sentences]:
        sentence = sentence.strip()
        if not sentence:
            continue
        selected.append(sentence)
        total_len += len(sentence)
        if total_len > 200:
            break

    return " ".join(selected)


def generate_monthly_summary(month_items, month_str):
    if not month_items:
        return f"# {month_str}の技術動向レポート\n\n今月の記事は見つかりませんでした。"

    scored_items = [
        item for item in month_items
        if item.get("score") is not None and safe_float(item.get("score", 0)) > 0
    ]
    if scored_items:
        top_items = sorted(scored_items, key=lambda item: -safe_float(item.get("score", 0)))[:10]
    else:
        top_items = sorted(
            month_items,
            key=lambda item: parse_datetime_safe(item.get("date", "")),
            reverse=True,
        )[:10]

    security_items = []
    ai_items = []
    tech_items = []

    for item in top_items:
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or item.get("description") or item.get("title") or "")
        if not summary:
            summary = title
        detail = "" if summary.strip() == title.strip() else summary

        text = f"{title} {summary}".lower()

        if any(keyword in text for keyword in [
            "セキュリティ", "security", "vulnerability", "cve", "exploit",
            "脆弱性", "breach", "attack", "ランサムウェア", "malware",
            "xss", "sql injection", "rce", "zero trust"
        ]):
            security_items.append({"title": title, "detail": detail})
        elif any(keyword in text for keyword in [
            "ai", "gpt", "llm", "人工知能", "機械学習", "openai",
            "anthropic", "claude", "gemini", "chatgpt", "transformer", "rag"
        ]):
            ai_items.append({"title": title, "detail": detail})
        else:
            tech_items.append({"title": title, "detail": detail})

    report_sections = []
    if security_items:
        content = "**セキュリティ動向 ({count}件)**\n\n".format(count=len(security_items))
        for idx, item in enumerate(security_items, 1):
            title = item["title"][:120]
            detail = extract_detail(item["detail"], max_sentences=3) if item.get("detail") else ""
            content += f"{idx}. {title}\n   {detail}\n\n" if detail else f"{idx}. {title}\n\n"
        report_sections.append(content.strip())

    if ai_items:
        content = "**AI・機械学習動向 ({count}件)**\n\n".format(count=len(ai_items))
        for idx, item in enumerate(ai_items, 1):
            title = item["title"][:120]
            detail = extract_detail(item["detail"], max_sentences=3) if item.get("detail") else ""
            content += f"{idx}. {title}\n   {detail}\n\n" if detail else f"{idx}. {title}\n\n"
        report_sections.append(content.strip())

    if tech_items:
        content = "**技術トレンド ({count}件)**\n\n".format(count=len(tech_items))
        for idx, item in enumerate(tech_items, 1):
            title = item["title"][:120]
            detail = extract_detail(item["detail"], max_sentences=2) if item.get("detail") else ""
            content += f"{idx}. {title}\n   {detail}\n\n" if detail else f"{idx}. {title}\n\n"
        report_sections.append(content.strip())

    if not report_sections:
        return f"# {month_str}の技術動向レポート\n\n今月の主要記事は検出できませんでした。"

    return f"# {month_str}の技術動向レポート\n\n" + "\n\n".join(report_sections)


def generate_html_report(archive_data, month_str):
    summary = archive_data.get("summary", "今月のまとめ")
    def render_summary_html(text):
        escaped_lines = [escape(line) for line in str(text).splitlines()]
        blocks = []
        for line in escaped_lines:
            if not line.strip():
                continue
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            if line.startswith("# "):
                blocks.append(f'<h2 class="report-title">{line[2:].strip()}</h2>')
            else:
                blocks.append(f"<p>{line}</p>")
        return "\n".join(blocks) if blocks else "<p>今月のまとめはありません。</p>"

    summary_html = render_summary_html(summary)

    top_articles = archive_data.get("top_articles", [])[:10]
    top_articles_html = ""
    if top_articles:
        top_articles_html = '<div class="section"><h2>🏆 Top 10 人気記事</h2><ul class="top-articles">'
        for idx, article in enumerate(top_articles, 1):
            title = escape(str(article.get("title_ja") or article.get("title") or ""))
            link = escape(str(article.get("link") or article.get("url") or "#"), quote=True)
            source = escape(str(article.get("source") or ""))
            score = article.get("score", 0)
            rank_class = "gold" if idx == 1 else "silver" if idx == 2 else "bronze" if idx == 3 else ""
            top_articles_html += f'''
            <li>
              <span class="rank {rank_class}">{idx}</span>
              <div class="article-title">{title}</div>
              <div class="article-meta">
                📡 {source} | 👍 {score}
                <a href="{link}" target="_blank" class="article-link">記事を読む →</a>
              </div>
            </li>'''
        top_articles_html += "</ul></div>"

    source_counts = archive_data.get("source_counts", {})
    source_stats_html = ""
    if source_counts:
        top_sources = sorted(source_counts.items(), key=lambda item: -item[1])[:10]
        source_stats_html = '<div class="section"><h2>📰 情報源別統計（Top 10）</h2><div class="source-list">'
        for source, count in top_sources:
            source_name = escape(str(source))
            source_stats_html += f'''
            <div class="source-item">
              <div class="source-name">{source_name}</div>
              <div class="source-count">{count}</div>
            </div>'''
        source_stats_html += "</div></div>"

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{month_str} 月次レポート - tech-feeds</title>
  <style>
    :root {{ --bg:#f6f8fa; --panel:#fff; --muted:#57606a; --border:#d0d7de; --text:#24292f; --accent:#0969da; --accent-strong:#0550ae; }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', Meiryo, sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; padding: 20px; }}
    .container {{ max-width: 1000px; margin: 0 auto; background: var(--panel); padding: 32px; border-radius: 8px; border: 1px solid var(--border); }}
    .header {{ border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }}
    .header h1 {{ font-size: 30px; color: var(--text); margin-bottom: 6px; }}
    .header .meta {{ font-size: 13px; color: var(--muted); }}
    .summary {{ background: var(--panel); border: 1px solid var(--border); padding: 20px; border-radius: 8px; margin-bottom: 24px; font-size: 15px; }}
    .summary h2 {{ font-size: 20px; margin-bottom: 10px; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
    .summary p {{ margin-bottom: 10px; color: var(--text); }}
    .summary strong {{ font-weight: 700; }}
    .section {{ margin-bottom: 28px; }}
    .section h2 {{ font-size: 22px; color: var(--text); margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .stat-card {{ background: var(--bg); border: 1px solid var(--border); padding: 16px; border-radius: 8px; text-align: center; }}
    .stat-card .number {{ font-size: 30px; font-weight: bold; color: var(--accent); margin-bottom: 4px; }}
    .stat-card .label {{ font-size: 13px; color: var(--muted); }}
    .top-articles {{ list-style: none; }}
    .top-articles li {{ background: var(--bg); border: 1px solid var(--border); padding: 12px; margin-bottom: 10px; border-radius: 8px; }}
    .top-articles .rank {{ display: inline-block; width: 28px; height: 28px; background: var(--accent); color: white; border-radius: 50%; text-align: center; line-height: 28px; font-weight: bold; margin-right: 8px; }}
    .top-articles .rank.gold {{ background: #9a6700; color: #fff; }}
    .top-articles .rank.silver {{ background: #57606a; color: #fff; }}
    .top-articles .rank.bronze {{ background: #8250df; color: #fff; }}
    .article-title {{ font-weight: 600; color: var(--text); font-size: 15px; margin-bottom: 5px; }}
    .article-meta {{ font-size: 12px; color: var(--muted); }}
    .article-link {{ color: var(--accent); text-decoration: none; font-size: 12px; margin-left: 10px; }}
    .article-link:hover {{ text-decoration: underline; }}
    .source-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
    .source-item {{ background: var(--bg); border: 1px solid var(--border); padding: 12px; border-radius: 8px; }}
    .source-name {{ font-weight: 600; color: var(--text); margin-bottom: 4px; }}
    .source-count {{ font-size: 22px; color: var(--accent); font-weight: bold; }}
    .footer {{ margin-top: 30px; padding-top: 16px; border-top: 1px solid var(--border); text-align: center; color: var(--muted); font-size: 13px; }}
    .back-link {{ display: inline-block; background: var(--accent); border: 1px solid var(--accent-strong); color: white; padding: 8px 14px; border-radius: 6px; text-decoration: none; margin-bottom: 16px; }}
    .back-link:hover {{ background: var(--accent-strong); }}
  </style>
</head>
<body>
  <div class="container">
    <a href="../../index.html" class="back-link">← トップページに戻る</a>
    <div class="header">
      <h1>{month_str} 月次レポート</h1>
      <div class="meta">tech-feeds - Monthly Archive</div>
    </div>
    <div class="summary">
      {summary_html}
    </div>
    <div class="section">
      <h2>📊 統計情報</h2>
      <div class="stats">
        <div class="stat-card">
          <div class="number">{archive_data['total_articles']}</div>
          <div class="label">総記事数</div>
        </div>
        <div class="stat-card">
          <div class="number">{len(archive_data.get('source_counts', {}))}</div>
          <div class="label">情報源数</div>
        </div>
        <div class="stat-card">
          <div class="number">{len(top_articles)}</div>
          <div class="label">Top記事</div>
        </div>
      </div>
    </div>
    {top_articles_html}
    {source_stats_html}
    <div class="footer">
      <p>Generated by tech-feeds</p>
      <p><a href="../../index.html" style="color: #0969da;">トップページに戻る</a></p>
    </div>
  </div>
</body>
</html>'''
    return html


def compress_old_archives(compress_before):
    compressed_count = 0
    for json_path in ARCHIVE_DIR.glob("*.json"):
        if json_path.name == "index.json":
            continue
        try:
            month_dt = datetime.strptime(json_path.stem, "%Y-%m").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if month_dt < compress_before:
            gz_path = json_path.with_suffix(".json.gz")
            if not gz_path.exists():
                with open(json_path, "rb") as fin:
                    with gzip.open(gz_path, "wb") as fout:
                        fout.writelines(fin)
                json_path.unlink()
                compressed_count += 1
    if compressed_count:
        print(f"[OK] Compressed {compressed_count} old archives")


def main():
    news_path = DATA_DIR / "news.json"
    if not news_path.exists():
        print("[ERROR] news.json not found")
        return

    with open(news_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    items = data.get("items", [])
    if not items:
        print("[ERROR] No items")
        return

    dates = [parse_datetime_safe(item.get("date", "")) for item in items if item.get("date")]
    if not dates:
        print("[ERROR] No valid dates")
        return

    min_month = min(dates).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    max_month = max(dates).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    current = min_month
    while current <= max_month:
        next_month = current.replace(year=current.year + 1, month=1) if current.month == 12 else current.replace(month=current.month + 1)
        month_str = current.strftime("%Y-%m")
        month_items = [
            item for item in items
            if current <= parse_datetime_safe(item.get("date", "")) < next_month
        ]

        source_counts = Counter(str(item.get("source") or "") for item in month_items)
        sev_counts = Counter(str(item.get("severity") or "") for item in month_items if item.get("severity"))
        scored_items = [item for item in month_items if item.get("score") is not None]
        top_articles = sorted(scored_items, key=lambda item: -safe_float(item.get("score", 0)))[:20]
        security_items = sorted(
            [item for item in month_items if str(item.get("severity") or "").lower() in {"critical", "high"}],
            key=lambda item: parse_datetime_safe(item.get("date", "")),
            reverse=True,
        )[:30]

        summary = generate_monthly_summary(month_items, month_str)
        archive_data = {
            "month": month_str,
            "total_articles": len(month_items),
            "summary": summary,
            "source_counts": dict(source_counts),
            "severity_counts": dict(sev_counts),
            "top_articles": top_articles,
            "security_highlights": security_items,
        }

        out_json = ARCHIVE_DIR / f"{month_str}.json"
        with open(out_json, "w", encoding="utf-8") as handle:
            json.dump(archive_data, handle, ensure_ascii=False, indent=2)

        html_path = ARCHIVE_DIR / f"{month_str}.html"
        with open(html_path, "w", encoding="utf-8") as handle:
            handle.write(generate_html_report(archive_data, month_str))

        print(f"[{month_str}] JSON + HTML ({len(month_items)} articles)")
        current = next_month

    compress_before = datetime.now(timezone.utc) - timedelta(days=30 * COMPRESS_MONTHS_AGO)
    compress_old_archives(compress_before)

    archive_files = []
    for json_path in ARCHIVE_DIR.glob("*.json"):
        if json_path.name == "index.json":
            continue
        with open(json_path, "r", encoding="utf-8") as handle:
            archive = json.load(handle)
        archive_files.append({
            "month": archive["month"],
            "total_articles": archive.get("total_articles", 0),
            "summary": archive.get("summary", ""),
            "file": json_path.name,
            "html_file": f"{archive['month']}.html",
            "compressed": False,
        })

    for gz_path in ARCHIVE_DIR.glob("*.json.gz"):
        with gzip.open(gz_path, "rt", encoding="utf-8") as handle:
            archive = json.load(handle)
        archive_files.append({
            "month": archive["month"],
            "total_articles": archive.get("total_articles", 0),
            "summary": archive.get("summary", ""),
            "file": gz_path.name,
            "html_file": f"{archive['month']}.html",
            "compressed": True,
        })

    archive_files.sort(key=lambda item: item["month"], reverse=True)
    index_path = ARCHIVE_DIR / "index.json"
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump({"months": archive_files}, handle, ensure_ascii=False, indent=2)

    print(f"[OK] index.json ({len(archive_files)} months)")


if __name__ == "__main__":
    main()
