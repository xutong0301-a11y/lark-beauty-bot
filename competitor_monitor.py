import datetime as dt
import html
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests
from dateutil import parser
from openai import OpenAI
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LARK_WEBHOOK_URL = os.environ.get("LARK_WEBHOOK_URL")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "7"))
MAX_PRODUCTS_PER_BRAND = int(os.environ.get("MAX_PRODUCTS_PER_BRAND", "6"))
MAX_TRENDS_PER_QUERY = int(os.environ.get("MAX_TRENDS_PER_QUERY", "3"))
SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "snapshots"))
DISABLE_AI = os.environ.get("DISABLE_AI", "").lower() in {"1", "true", "yes"}
SEND_EMPTY_REPORT = os.environ.get("SEND_EMPTY_REPORT", "").lower() in {"1", "true", "yes"}
MAX_LARK_MARKDOWN_CHARS = int(os.environ.get("MAX_LARK_MARKDOWN_CHARS", "9000"))
INCLUDE_PRODUCT_UPDATES = os.environ.get("INCLUDE_PRODUCT_UPDATES", "").lower() in {"1", "true", "yes"}
EXCLUDE_PRODUCT_PATTERN = re.compile(
    os.environ.get(
        "EXCLUDE_PRODUCT_PATTERN",
        r"shipping protection|route package protection|freegift|free gift|100% off|gift card|peel\s*&\s*sniff|sample",
    ),
    re.IGNORECASE,
)


COMPETITORS = [
    {"brand": "Fenty Beauty", "base_url": "https://fentybeauty.com"},
    {"brand": "fwee", "base_url": "https://fwee.us"},
    {"brand": "Kaja Beauty", "base_url": "https://kajabeauty.com"},
    {"brand": "Kylie Cosmetics", "base_url": "https://kyliecosmetics.com"},
    {"brand": "Milk Makeup", "base_url": "https://milkmakeup.com"},
    {"brand": "Sacheu", "base_url": "https://sacheu.com"},
    {"brand": "Summer Fridays", "base_url": "https://summerfridays.com"},
    {"brand": "Tarte Cosmetics", "base_url": "https://tartecosmetics.com"},
    {"brand": "Laneige US", "base_url": "https://us.laneige.com"},
    {"brand": "Wonderskin", "base_url": "https://wonderskin.com"},
    {"brand": "Charlotte Tilbury", "base_url": "https://www.charlottetilbury.com"},
    {"brand": "Glossier", "base_url": "https://www.glossier.com"},
    {"brand": "Merit Beauty", "base_url": "https://www.meritbeauty.com"},
    {"brand": "Pixi Beauty", "base_url": "https://www.pixibeauty.com"},
    {"brand": "Rare Beauty", "base_url": "https://www.rarebeauty.com"},
    {"brand": "Rhode", "base_url": "https://www.rhodeskin.com"},
    {"brand": "SHEGLAM", "base_url": "https://www.sheglam.com"},
    {"brand": "Tower 28", "base_url": "https://www.tower28beauty.com"},
    {"brand": "Westman Atelier", "base_url": "https://www.westman-atelier.com"},
]


TREND_QUERIES = [
    {
        "label": "TikTok Shop US policy",
        "query": "TikTok Shop US Seller Center policy rules beauty sellers",
    },
    {
        "label": "US TikTok beauty commerce",
        "query": "TikTok Shop US beauty brand launch creator affiliate",
    },
    {
        "label": "Viral beauty on TikTok",
        "query": "viral beauty skincare makeup trend TikTok USA",
    },
    {
        "label": "K-beauty launches",
        "query": "K-beauty skincare makeup innovation launch US",
    },
    {
        "label": "Beauty consumer trends",
        "query": "beauty market consumer trend skincare makeup",
    },
]


PROMPT_TEMPLATE = """
你是一名谨慎的美妆行业竞品分析师。下面是一份结构化 JSON，包含两类信息：
1. products：来自品牌独立站公开接口的商品信号，证据等级为 high。它可以表述为“官网新品/商品更新信号”，但不要断言销量、爆款或平台表现。
2. trends：来自 Google News RSS 的新闻搜索线索，证据等级为 medium。它只能表述为“趋势线索/新闻线索”，不得当作已经核验的事实。

请基于 JSON 生成一份发送到飞书/Lark 的中文 Markdown 周报。必须遵守：
- 只能使用 JSON 里的信息，不要补编新闻、链接、日期、销量、评论数或平台政策细节。
- 不要使用 # / ## 标题，用 **【小标题】** 这类格式。
- 每条产品必须带品牌、商品名、信号日期、日期依据、链接。
- 每条趋势必须带标题、媒体、发布时间、链接，并标注“新闻搜索线索，需人工复核”。
- 加一个 **【采集健康】** 板块，说明哪些品牌无近 7 天信号、哪些源请求失败。
- 如果某类信息不足，直接写“本期未抓到足够信号”，不要扩写。

JSON：
{raw_json}
"""


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def parse_datetime(value):
    if not value:
        return None
    try:
        parsed = parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def display_date(value):
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if not parsed:
        return "未知时间"
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")


def clean_text(value):
    if not value:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def is_noise_product(title, url=""):
    haystack = f"{title} {url}"
    return bool(EXCLUDE_PRODUCT_PATTERN.search(haystack))


def create_session():
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept": "application/xml,application/atom+xml,application/json,text/html;q=0.8,*/*;q=0.5",
        }
    )
    return session


def request_get(session, url, timeout=18):
    started = time.perf_counter()
    try:
        response = session.get(url, timeout=timeout)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return response, None, elapsed_ms
    except requests.RequestException as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return None, f"{type(exc).__name__}: {exc}", elapsed_ms


def within_lookback(parsed_dt, reference_time, days):
    if not parsed_dt:
        return False
    return dt.timedelta(days=-1) <= reference_time - parsed_dt <= dt.timedelta(days=days)


def extract_image_url(summary_html):
    if not summary_html:
        return ""
    match = re.search(r'src=["\']([^"\']+)["\']', summary_html)
    return html.unescape(match.group(1)) if match else ""


def product_url(base_url, handle):
    if not handle:
        return base_url.rstrip("/")
    return f"{base_url.rstrip('/')}/products/{handle}"


def source_status(source, url, brand, response=None, error=None, elapsed_ms=None):
    return {
        "brand": brand,
        "source": source,
        "url": url,
        "ok": response is not None and response.ok and not error,
        "status_code": response.status_code if response is not None else None,
        "content_type": response.headers.get("content-type", "") if response is not None else "",
        "elapsed_ms": elapsed_ms,
        "error": error or "",
        "items_seen": 0,
        "recent_items": 0,
    }


def fetch_atom_products(session, competitor, reference_time):
    brand = competitor["brand"]
    base_url = competitor["base_url"].rstrip("/")
    feed_url = f"{base_url}/collections/all.atom"
    print(f"Checking Atom feed: {brand} -> {feed_url}")

    response, error, elapsed_ms = request_get(session, feed_url)
    status = source_status("shopify_atom", feed_url, brand, response, error, elapsed_ms)
    if error or response is None or response.status_code != 200:
        if not error and response is not None:
            status["error"] = f"HTTP {response.status_code}"
            status["ok"] = False
        return [], status

    products = []
    try:
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns) or root.findall(".//entry")
        status["items_seen"] = len(entries)

        for entry in entries:
            title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
            link_element = entry.find("atom:link", ns)
            link = link_element.attrib.get("href", "") if link_element is not None else ""
            if is_noise_product(title, link):
                continue
            published_raw = entry.findtext("atom:published", default="", namespaces=ns)
            updated_raw = entry.findtext("atom:updated", default="", namespaces=ns)
            signal_dt = parse_datetime(published_raw) or parse_datetime(updated_raw)
            if not within_lookback(signal_dt, reference_time, LOOKBACK_DAYS):
                continue

            summary_raw = entry.findtext("atom:summary", default="", namespaces=ns)
            status["recent_items"] += 1
            products.append(
                {
                    "brand": brand,
                    "title": title,
                    "url": link,
                    "image_url": extract_image_url(summary_raw),
                    "signal_type": "new_or_republished_product",
                    "signal_date": signal_dt.isoformat(),
                    "date_basis": "Shopify Atom published" if published_raw else "Shopify Atom updated",
                    "published_at": published_raw,
                    "updated_at": updated_raw,
                    "evidence_level": "high",
                    "source_method": "brand_site_atom",
                    "source_url": feed_url,
                }
            )
    except ET.ParseError as exc:
        status["ok"] = False
        status["error"] = f"XML ParseError: {exc}"

    return products, status


def fetch_products_json(session, competitor, reference_time):
    brand = competitor["brand"]
    base_url = competitor["base_url"].rstrip("/")
    json_url = f"{base_url}/products.json?limit=250"
    print(f"Checking products.json: {brand} -> {json_url}")

    response, error, elapsed_ms = request_get(session, json_url)
    status = source_status("shopify_products_json", json_url, brand, response, error, elapsed_ms)
    if error or response is None or response.status_code != 200:
        if not error and response is not None:
            status["error"] = f"HTTP {response.status_code}"
            status["ok"] = False
        return [], status

    products = []
    try:
        payload = response.json()
        raw_products = payload.get("products", [])
        status["items_seen"] = len(raw_products)

        for item in raw_products:
            title = clean_text(item.get("title", ""))
            handle = item.get("handle", "")
            url = product_url(base_url, handle)
            if is_noise_product(title, url):
                continue

            published_at = item.get("published_at")
            created_at = item.get("created_at")
            updated_at = item.get("updated_at")
            candidates = [
                ("Shopify products.json published_at", parse_datetime(published_at), published_at),
                ("Shopify products.json created_at", parse_datetime(created_at), created_at),
            ]
            if INCLUDE_PRODUCT_UPDATES:
                candidates.append(("Shopify products.json updated_at", parse_datetime(updated_at), updated_at))
            selected = next(
                (
                    (basis, parsed_dt, raw_value)
                    for basis, parsed_dt, raw_value in candidates
                    if within_lookback(parsed_dt, reference_time, LOOKBACK_DAYS)
                ),
                None,
            )
            if not selected:
                continue

            basis, signal_dt, _raw_value = selected
            images = item.get("images") or []
            image_url = images[0].get("src", "") if images else ""
            status["recent_items"] += 1
            products.append(
                {
                    "brand": brand,
                    "title": title,
                    "url": url,
                    "image_url": image_url,
                    "signal_type": "product_update" if "updated_at" in basis else "new_or_published_product",
                    "signal_date": signal_dt.isoformat(),
                    "date_basis": basis,
                    "published_at": published_at,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "product_type": clean_text(item.get("product_type", "")),
                    "vendor": clean_text(item.get("vendor", "")),
                    "tags": item.get("tags", []),
                    "evidence_level": "high",
                    "source_method": "brand_site_products_json",
                    "source_url": json_url,
                }
            )
    except (ValueError, TypeError) as exc:
        status["ok"] = False
        status["error"] = f"JSON ParseError: {exc}"

    return products, status


def dedupe_products(products):
    deduped = {}
    for product in products:
        normalized_title = re.sub(r"\W+", " ", product.get("title", "").lower()).strip()
        key = (
            product.get("brand", "").lower(),
            normalized_title or product.get("url", ""),
        )
        if key not in deduped:
            product["source_methods"] = [product.pop("source_method")]
            product["evidence_urls"] = [product.get("source_url", "")]
            deduped[key] = product
            continue

        existing = deduped[key]
        method = product.get("source_method")
        if method and method not in existing["source_methods"]:
            existing["source_methods"].append(method)
        source_url = product.get("source_url", "")
        if source_url and source_url not in existing["evidence_urls"]:
            existing["evidence_urls"].append(source_url)

    return sorted(
        deduped.values(),
        key=lambda item: parse_datetime(item.get("signal_date")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        reverse=True,
    )


def dedupe_trends(trends):
    deduped = {}
    for trend in trends:
        normalized_title = re.sub(r"\W+", " ", trend.get("title", "").lower()).strip()
        key = normalized_title or trend.get("google_news_url", "")
        if key not in deduped:
            deduped[key] = trend
            continue

        existing = deduped[key]
        if trend["topic"] not in existing["topic"].split(" / "):
            existing["topic"] = f"{existing['topic']} / {trend['topic']}"

    return sorted(
        deduped.values(),
        key=lambda item: parse_datetime(item.get("published_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        reverse=True,
    )


def collect_competitor_products(session, reference_time):
    all_products = []
    statuses = []

    for competitor in COMPETITORS:
        atom_products, atom_status = fetch_atom_products(session, competitor, reference_time)
        json_products, json_status = fetch_products_json(session, competitor, reference_time)
        all_products.extend(atom_products)
        all_products.extend(json_products)
        statuses.extend([atom_status, json_status])
        time.sleep(0.25)

    return dedupe_products(all_products), statuses


def fetch_news_trends(session, reference_time):
    trends = []
    statuses = []
    for query in TREND_QUERIES:
        search_query = f"{query['query']} when:{LOOKBACK_DAYS}d"
        encoded_query = urllib.parse.quote(search_query)
        feed_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        print(f"Checking trend RSS: {query['label']} -> {feed_url}")

        response, error, elapsed_ms = request_get(session, feed_url, timeout=20)
        status = source_status("google_news_rss", feed_url, query["label"], response, error, elapsed_ms)
        if error or response is None or response.status_code != 200:
            if not error and response is not None:
                status["error"] = f"HTTP {response.status_code}"
                status["ok"] = False
            statuses.append(status)
            continue

        try:
            root = ET.fromstring(response.content)
            items = root.findall(".//item")
            status["items_seen"] = len(items)
            kept = 0
            for item in items:
                if kept >= MAX_TRENDS_PER_QUERY:
                    break
                pub_date_raw = item.findtext("pubDate", default="")
                pub_dt = parse_datetime(pub_date_raw)
                if not within_lookback(pub_dt, reference_time, LOOKBACK_DAYS):
                    continue

                source = item.find("source")
                source_name = source.text if source is not None else ""
                source_url = source.attrib.get("url", "") if source is not None else ""
                trends.append(
                    {
                        "topic": query["label"],
                        "title": clean_text(item.findtext("title", default="")),
                        "publisher": clean_text(source_name),
                        "publisher_url": source_url,
                        "published_at": pub_dt.isoformat() if pub_dt else pub_date_raw,
                        "date_basis": "Google News RSS pubDate",
                        "google_news_url": item.findtext("link", default=""),
                        "evidence_level": "medium",
                        "source_method": "google_news_search",
                        "review_note": "新闻搜索线索，需人工复核原文。",
                    }
                )
                kept += 1
                status["recent_items"] += 1
        except ET.ParseError as exc:
            status["ok"] = False
            status["error"] = f"XML ParseError: {exc}"

        statuses.append(status)
        time.sleep(0.5)

    return dedupe_trends(trends), statuses


def summarize_statuses(statuses):
    failed = [
        {
            "brand_or_topic": item["brand"],
            "source": item["source"],
            "status_code": item["status_code"],
            "error": item["error"],
            "url": item["url"],
        }
        for item in statuses
        if not item["ok"]
    ]
    no_recent_by_brand = []
    for competitor in COMPETITORS:
        brand = competitor["brand"]
        brand_statuses = [item for item in statuses if item["brand"] == brand]
        if brand_statuses and sum(item.get("recent_items", 0) for item in brand_statuses) == 0:
            no_recent_by_brand.append(brand)

    return {
        "total_sources": len(statuses),
        "ok_sources": sum(1 for item in statuses if item["ok"]),
        "failed_sources": failed,
        "brands_without_recent_product_signal": no_recent_by_brand,
    }


def build_snapshot(products, trends, statuses, reference_time):
    limited_products = []
    by_brand_counts = {}
    for product in products:
        brand = product["brand"]
        by_brand_counts[brand] = by_brand_counts.get(brand, 0) + 1
        if by_brand_counts[brand] <= MAX_PRODUCTS_PER_BRAND:
            limited_products.append(product)

    snapshot = {
        "generated_at": reference_time.isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "note": (
            "products are high-confidence brand-site signals; trends are medium-confidence news-search leads. "
            "products.json updated_at is ignored by default because many stores batch-update old products."
        ),
        "products": limited_products,
        "product_count_total": len(products),
        "trends": trends,
        "trend_count_total": len(trends),
        "collection_health": summarize_statuses(statuses),
        "source_statuses": statuses,
    }
    return snapshot


def save_snapshot(snapshot):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().strftime("%Y%m%d_%H%M%SZ")
    dated_path = SNAPSHOT_DIR / f"competitor_snapshot_{stamp}.json"
    latest_path = SNAPSHOT_DIR / "latest_competitor_snapshot.json"
    for path in (dated_path, latest_path):
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidence snapshot saved: {dated_path}")
    return dated_path


def product_line(product):
    return (
        f"- **{product['brand']}** | {product['title']}\n"
        f"  信号日期: {display_date(product.get('signal_date'))} | "
        f"依据: {product.get('date_basis', '未知')} | "
        f"[官网链接]({product.get('url', '')})"
    )


def trend_line(trend):
    return (
        f"- **{trend['topic']}** | {trend['title']}\n"
        f"  媒体: {trend.get('publisher') or '未知媒体'} | "
        f"发布时间: {display_date(trend.get('published_at'))} | "
        f"[Google News线索]({trend.get('google_news_url', '')}) | 新闻搜索线索，需人工复核"
    )


def build_fallback_report(snapshot):
    lines = [
        f"**【竞品独立站新品与趋势周报】**",
        f"采集时间: {display_date(snapshot['generated_at'])} | 回看窗口: {snapshot['lookback_days']} 天",
        "",
        "**【官网新品/商品更新信号】**",
    ]

    if snapshot["products"]:
        grouped = {}
        for product in snapshot["products"]:
            grouped.setdefault(product["brand"], []).append(product)

        def newest_signal(items):
            dates = [parse_datetime(item.get("signal_date")) for item in items]
            dates = [item for item in dates if item]
            return max(dates) if dates else dt.datetime.min.replace(tzinfo=dt.timezone.utc)

        for brand, items in sorted(grouped.items(), key=lambda pair: newest_signal(pair[1]), reverse=True):
            lines.append(f"\n**{brand}**")
            for product in items:
                lines.append(product_line(product))
    else:
        lines.append("本期未抓到足够信号。")

    lines.extend(["", "**【趋势与平台线索】**"])
    if snapshot["trends"]:
        for trend in snapshot["trends"]:
            lines.append(trend_line(trend))
    else:
        lines.append("本期未抓到足够信号。")

    health = snapshot["collection_health"]
    failed = health["failed_sources"][:8]
    no_recent = health["brands_without_recent_product_signal"][:20]
    lines.extend(
        [
            "",
            "**【采集健康】**",
            f"- 源状态: {health['ok_sources']}/{health['total_sources']} 个源请求成功。",
            f"- 无近 {snapshot['lookback_days']} 天官网商品信号: {', '.join(no_recent) if no_recent else '无'}",
        ]
    )
    if failed:
        lines.append("- 请求失败源:")
        for item in failed:
            reason = item["error"] or f"HTTP {item['status_code']}"
            lines.append(f"  - {item['brand_or_topic']} / {item['source']}: {reason}")
    else:
        lines.append("- 请求失败源: 无")

    return "\n".join(lines)


def generate_report(snapshot):
    if DISABLE_AI or not DEEPSEEK_API_KEY:
        print("DeepSeek disabled or missing; using deterministic fallback report.")
        return build_fallback_report(snapshot)

    print("Calling DeepSeek to generate Lark report...")
    raw_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    prompt = PROMPT_TEMPLATE.replace("{raw_json}", raw_json)
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是谨慎的竞品情报分析师，只能基于用户提供的结构化证据写报告。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as exc:
        print(f"DeepSeek failed: {exc}")
        fallback = build_fallback_report(snapshot)
        return f"**【AI生成失败，以下为规则化报告】**\n{fallback}"


def truncate_for_lark(content):
    if len(content) <= MAX_LARK_MARKDOWN_CHARS:
        return content
    return (
        content[:MAX_LARK_MARKDOWN_CHARS]
        + "\n\n**【内容已截断】**\n完整原始证据请查看 workflow artifact 或 snapshots/latest_competitor_snapshot.json。"
    )


def send_to_lark(content):
    if not LARK_WEBHOOK_URL:
        print("LARK_WEBHOOK_URL not configured; skipping Lark send.")
        return

    print("Sending report to Lark...")
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"竞品独立站新品与趋势周报 ({dt.datetime.now().strftime('%m-%d')})",
                },
                "template": "blue",
            },
            "elements": [{"tag": "markdown", "content": truncate_for_lark(content)}],
        },
    }

    try:
        response = requests.post(
            LARK_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=15,
        )
        if response.status_code != 200:
            print(f"Lark send failed: HTTP {response.status_code}, {response.text}")
            return
        try:
            result = response.json()
            if result.get("code") not in (None, 0):
                print(f"Lark returned non-zero code: {result}")
            else:
                print("Lark report sent.")
        except ValueError:
            print("Lark report sent; response was not JSON.")
    except requests.RequestException as exc:
        print(f"Lark send request failed: {exc}")


def main():
    reference_time = now_utc()
    print(f"[{reference_time.isoformat()}] Starting competitor intelligence run...")
    print(f"Lookback window: {LOOKBACK_DAYS} days")

    session = create_session()
    products, product_statuses = collect_competitor_products(session, reference_time)
    trends, trend_statuses = fetch_news_trends(session, reference_time)
    statuses = product_statuses + trend_statuses
    snapshot = build_snapshot(products, trends, statuses, reference_time)
    save_snapshot(snapshot)

    if not snapshot["products"] and not snapshot["trends"] and not SEND_EMPTY_REPORT:
        print("No product or trend signals found; not sending empty report.")
        return

    report = generate_report(snapshot)
    print("\n--- Report preview ---\n")
    print(report)
    print("\n----------------------\n")
    send_to_lark(report)
    print("Competitor intelligence run finished.")


if __name__ == "__main__":
    main()
