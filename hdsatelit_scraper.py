
import csv
import json
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


# CONFIGURARE
BASE_URL = "https://www.hdsatelit.com"

PAGES = [
    BASE_URL + "/",
    BASE_URL + "/search/label/Stiri/",
]

FOLDER = Path(__file__).resolve().parent

CSV_FILE = FOLDER / "hdsatelit_articole.csv"
RSS_FILE = FOLDER / "hdsatelit.xml"
STATE_FILE = FOLDER / "hdsatelit_state.json"

MAX_ARTICLES = 100

ARTICLE_PATH = re.compile(
    r"^/20\d{2}/(?:0[1-9]|1[0-2])/[^/]+\.html$",
    re.IGNORECASE,
)


def extract_articles(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    articles = {}

    for link in soup.select("a[href]"):
        href = urljoin(source_url, link.get("href", ""))
        parsed = urlsplit(href)

        if parsed.hostname not in (
            "hdsatelit.com",
            "www.hdsatelit.com",
        ):
            continue

        if not ARTICLE_PATH.fullmatch(parsed.path):
            continue

        url = BASE_URL + parsed.path

        title = link.get_text(" ", strip=True)

        if len(title) < 15:
            title = link.get("title", "").strip()

        title = " ".join(title.split())

        if len(title) < 15:
            continue

        if url not in articles:
            articles[url] = title
        elif len(title) > len(articles[url]):
            articles[url] = title

    return articles


def download_articles():
    found = {}

    headers = {
        "User-Agent": "Mozilla/5.0 HD-Satelit-RSS/1.0",
        "Accept-Language": "ro-RO,ro;q=0.9",
    }

    with requests.Session() as session:
        session.headers.update(headers)

        for page in PAGES:
            print(f"Verific: {page}")

            try:
                response = session.get(
                    page,
                    timeout=25,
                )
                response.raise_for_status()
            except requests.RequestException as error:
                print(f"Eroare la accesare: {error}")
                continue

            articles = extract_articles(
                response.text,
                response.url,
            )

            for url, title in articles.items():
                if url not in found:
                    found[url] = title

            print(
                f"Articole identificate pe pagina: "
                f"{len(articles)}"
            )

    return found


def load_state():
    if not STATE_FILE.exists():
        return {}

    with STATE_FILE.open(
        "r", encoding="utf-8"
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Fisierul de stare are un format invalid."
        )

    return data


def save_csv(items):
    with CSV_FILE.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "Titlu",
            "Link",
            "Prima detectare UTC",
        ])

        for item in items:
            writer.writerow([
                item["title"],
                item["url"],
                item["first_seen"],
            ])


def save_rss(items):
    rss = ET.Element(
        "rss",
        attrib={"version": "2.0"},
    )

    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = (
        "HD Satelit - RSS personal"
    )

    ET.SubElement(channel, "link").text = BASE_URL

    ET.SubElement(channel, "description").text = (
        "Titluri si linkuri catre articolele HD Satelit"
    )

    ET.SubElement(channel, "language").text = "ro-RO"

    ET.SubElement(channel, "lastBuildDate").text = (
        format_datetime(datetime.now(timezone.utc))
    )

    for article in items:
        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = (
            article["title"]
        )

        ET.SubElement(item, "link").text = (
            article["url"]
        )

        ET.SubElement(
            item,
            "guid",
            attrib={"isPermaLink": "true"},
        ).text = article["url"]

        ET.SubElement(item, "description").text = (
            "Citeste articolul pe HD Satelit."
        )

        first_seen = datetime.fromisoformat(
            article["first_seen"]
        )

        ET.SubElement(item, "pubDate").text = (
            format_datetime(first_seen)
        )

    tree = ET.ElementTree(rss)

    ET.indent(tree, space="  ")

    tree.write(
        RSS_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    print("=" * 55)
    print("HD SATELIT - WEB SCRAPER SI GENERATOR RSS")
    print("=" * 55)

    articles = download_articles()

    if not articles:
        print(
            "Nu am identificat articole. "
            "Verifica accesul la site sau structura HTML."
        )
        return

    saved = load_state()
    now = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )

    new_count = 0

    for position, (url, title) in enumerate(
        articles.items()
    ):
        if url not in saved:
            saved[url] = {
                "url": url,
                "title": title,
                "first_seen": now,
                "position": position,
            }

            new_count += 1
        else:
            saved[url]["title"] = title

    ordered = sorted(
        saved.values(),
        key=lambda item: (
            item["first_seen"],
            -item.get("position", 0),
        ),
        reverse=True,
    )[:MAX_ARTICLES]

    state = {
        item["url"]: item
        for item in ordered
    }

    with STATE_FILE.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )

    save_csv(ordered)
    save_rss(ordered)

    print()
    print(f"Articole gasite acum: {len(articles)}")
    print(f"Articole noi: {new_count}")
    print(f"Articole pastrate: {len(ordered)}")

    print()
    print("Ultimele articole detectate:")

    for item in ordered[:5]:
        print(" -", item["title"])

    print()
    print("Fisiere generate:")
    print(CSV_FILE)
    print(RSS_FILE)
    print(STATE_FILE)

    print()
    print("Operatiune finalizata.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Eroare: {error}")
