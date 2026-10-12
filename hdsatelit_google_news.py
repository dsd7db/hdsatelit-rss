"""Flux RSS HD Satelit folosind rezultatele Google News, fara accesarea directa a site-ului."""
import csv
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent
RSS_FILE = ROOT / "hdsatelit.xml"
CSV_FILE = ROOT / "hdsatelit_articole.csv"
STATE_FILE = ROOT / "hdsatelit_google_state.json"
MAX_ARTICLES = 100

QUERIES = [
    "site:hdsatelit.com when:30d",
    "site:hdsatelit.com",
]


def google_news_url(query):
    return "https://news.google.com/rss/search?" + urlencode({
        "q": query,
        "hl": "ro",
        "gl": "RO",
        "ceid": "RO:ro",
    })


def as_utc(value):
    try:
        result = parsedate_to_datetime(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return datetime.now(timezone.utc)


def fetch_articles():
    errors = []
    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "HD-Satelit-RSS-Hobby/1.0 (public news aggregation)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        })
        for query in QUERIES:
            url = google_news_url(query)
            print("Interogare Google News:", query, flush=True)
            try:
                response = session.get(url, timeout=30)
                response.raise_for_status()
                channel = ET.fromstring(response.content).find("channel")
                if channel is None:
                    raise ValueError("Raspunsul nu contine un canal RSS")
                articles = {}
                for item in channel.findall("item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    source = item.find("source")
                    if source is not None:
                        publisher = (source.text or "").strip()
                        if publisher and publisher.lower() not in title.lower():
                            # Ne bazam pe cautarea site:, nu pe eticheta publicatiei.
                            pass
                        if publisher and title.endswith(" - " + publisher):
                            title = title[:-(len(publisher) + 3)].strip()
                    if not title or not link.startswith("https://news.google.com/"):
                        continue
                    date = as_utc(item.findtext("pubDate"))
                    articles[link] = {
                        "url": link,
                        "title": title,
                        "published": date.isoformat(timespec="seconds"),
                    }
                print("Articole primite:", len(articles), flush=True)
                if articles:
                    return list(articles.values())
                errors.append(query + ": flux RSS fara articole")
            except (requests.RequestException, ET.ParseError, ValueError) as exc:
                errors.append(query + ": " + str(exc))
                print("Eroare sursa:", exc, flush=True)

    raise RuntimeError("Nu s-au obtinut articole de la Google News. " + " | ".join(errors))


def load_history():
    if not STATE_FILE.exists():
        return {}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Istoricul articolelor trebuie sa fie un obiect JSON")
    return data


def write_rss(articles):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, value in [
        ("title", "HD Satelit - agregare Google News"),
        ("link", "https://www.hdsatelit.com/"),
        ("description", "Titluri HD Satelit preluate din indexul Google News; pot lipsi articole."),
        ("language", "ro-RO"),
        ("lastBuildDate", format_datetime(datetime.now(timezone.utc))),
    ]:
        ET.SubElement(channel, tag).text = value

    for article in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article["url"]
        ET.SubElement(item, "guid", isPermaLink="true").text = article["url"]
        ET.SubElement(item, "description").text = "Deschide articolul HD Satelit prin Google News."
        published = datetime.fromisoformat(article["published"])
        ET.SubElement(item, "pubDate").text = format_datetime(published)

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)


def main():
    fetched = fetch_articles()
    saved = load_history()
    new_count = 0
    for article in fetched:
        key = article["url"]
        if key not in saved:
            new_count += 1
        saved[key] = article

    sorted_articles = sorted(
        saved.values(), key=lambda article: article["published"], reverse=True
    )[:MAX_ARTICLES]

    if not sorted_articles:
        raise RuntimeError("Nu exista articole de publicat")

    write_rss(sorted_articles)
    with CSV_FILE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Titlu", "Link Google News", "Data publicarii UTC"])
        for article in sorted_articles:
            writer.writerow([article["title"], article["url"], article["published"]])

    STATE_FILE.write_text(
        json.dumps({item["url"]: item for item in sorted_articles},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"RSS valid generat: {RSS_FILE.name}; articole: {len(sorted_articles)}; noi: {new_count}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as error:
        print("EROARE: " + str(error), file=sys.stderr, flush=True)
        sys.exit(1)
