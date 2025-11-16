#!/usr/bin/env python3
"""
Henter kulturprogrammet fra fauskekino.no og lagrer:

- data/kultur_program_raw.json  (rådata fra API)
- data/kultur_program.json      (ryddig struktur for app/debug)

Kjør:
    cd ~/Documents/fauske.kommune/scraper
    source venv/bin/activate
    python3 scrape_fauskekino_kultur.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://www.fauskekino.no"
API_URL = f"{BASE_URL}/api/culture?includeDocuments=true&first=500"

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_PATH = DATA_DIR / "kultur_program_raw.json"
OUT_PATH = DATA_DIR / "kultur_program.json"


def fetch_culture_raw() -> dict:
    resp = requests.get(API_URL, timeout=20)
    resp.raise_for_status()
    return resp.json()


def build_program(raw_wrapper: dict) -> dict:
    """
    Bygger en ryddig liste med arrangement fra:
    - raw["shows"] (forestillinger)
    - raw["fwpakkeArticles"] (omtaler/bilder per KUL-nummer)
    """
    raw = raw_wrapper  # API-responsen er allerede det som ligger under "raw" i *_raw.json
    shows = raw.get("shows", [])
    articles = raw.get("fwpakkeArticles", {})

    events_by_kul = {}

    for show in shows:
        kul = show.get("movieVersionId")
        title = show.get("movieTitle")

        if not kul:
            continue

        ev = events_by_kul.get(kul)
        if not ev:
            art = articles.get(kul, {})
            art_title = art.get("title") or title

            ev = {
                "id": kul,
                "title": art_title or title,
                "movieTitle": title,
                "url": f"{BASE_URL}/kulturprogram/{kul}",
                "shows": [],
            }
            events_by_kul[kul] = ev

        ev["shows"].append(
            {
                "screenName": show.get("screenName"),
                "ticketSaleUrl": show.get("ticketSaleUrl"),
                "showStart": show.get("showStart"),
                "showType": show.get("showType"),
            }
        )

    events = list(events_by_kul.values())
    events.sort(key=lambda e: (e["shows"][0]["showStart"] if e["shows"] else ""))

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }


def main() -> None:
    print("Henter kulturprogram fra API ...")
    api_data = fetch_culture_raw()

    # 1) Lagre rådata
    wrapper = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "raw": api_data,
    }
    RAW_PATH.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Skrev rådata til {RAW_PATH}")

    # 2) Lag ryddig program basert på shows + fwpakkeArticles
    program = build_program(api_data)
    OUT_PATH.write_text(
        json.dumps(program, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Skrev forenklet kulturprogram til {OUT_PATH}")


if __name__ == "__main__":
    main()