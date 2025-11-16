#!/usr/bin/env python3
"""
Henter hele kinoprogrammet fra fauskekino.no sitt API og lagrer:

- data/fauskekino_program_raw.json  (rådata fra API-et)
- data/fauskekino_program.json      (forenklet program som er lett å bruke i appen)

Kjør:
    cd /Users/fauskekino/Documents/fauske.kommune/scraper
    python3 scrape_fauskekino_program.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://www.fauskekino.no"
PROGRAM_ENDPOINT = (
    f"{BASE_URL}/api/program?date=alle&includeDocuments=true&groupMovies=true"
)

# Finn /data-mappa relativt til dette skriptet
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_PATH = DATA_DIR / "fauskekino_program_raw.json"
PROGRAM_SIMPLIFIED_PATH = DATA_DIR / "fauskekino_program.json"


def fetch_program() -> dict:
    """Henter kinoprogrammet fra API-et."""
    resp = requests.get(PROGRAM_ENDPOINT, timeout=20)
    resp.raise_for_status()
    return resp.json()


def save_raw(data: dict) -> None:
    """Lagrer rådata fra API-et til fauskekino_program_raw.json."""
    wrapper = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "raw": data,
    }
    RAW_PATH.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_simplified(raw_data: dict) -> dict:
    """
    Lager en litt enklere struktur for programmet:
    - En liste med filmer, hver med showtimes, sal, billettlenke og tags.
    """
    movies_out = []

    movies = raw_data.get("movies", [])
    for movie in movies:
        shows_out = []
        for show in movie.get("shows", []):
            shows_out.append(
                {
                    "showId": show.get("id"),
                    "start": show.get("showStart"),
                    "screen": show.get("screenName"),
                    "ticketUrl": show.get("ticketSaleUrl"),
                    "tags": [
                        t.get("tag")
                        for t in (show.get("versionTags") or [])
                        if t.get("tag")
                    ],
                }
            )

        movies_out.append(
            {
                # EDI-ID / film-ID (brukes videre mot filmwebMovies)
                "id": movie.get("mainVersionId") or movie.get("mainVersionEDI"),
                "title": movie.get("title"),
                "slug": movie.get("url"),
                "movieType": movie.get("movieType"),
                "isAdvanceSale": movie.get("isAdvanceSale"),
                "is3D": movie.get("is3D"),
                "isSubtitled": movie.get("isSubtitled"),
                "ageLimit": movie.get("ageLimit"),
                "shows": shows_out,
            }
        )

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "movies": movies_out,
    }


def main() -> None:
    print("Henter fullt kinoprogram fra fauskekino.no ...")
    api_data = fetch_program()

    # 1) Lagre rådata (inkludert filmwebMovies)
    save_raw(api_data)
    print(f"Skrev rådata for kinoprogram til {RAW_PATH}")

    # 2) Lagre forenklet program
    simplified = build_simplified(api_data)
    PROGRAM_SIMPLIFIED_PATH.write_text(
        json.dumps(simplified, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Skrev forenklet program til {PROGRAM_SIMPLIFIED_PATH}")


if __name__ == "__main__":
    main()