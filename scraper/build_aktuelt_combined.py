#!/usr/bin/env python3
"""
Bygger en felles Aktuelt-feed ved å kombinere:

- data/nyheter.json           (Fauske kommune)
- data/fauskenf_nyheter.json  (Fauske Næringsforum)

Output:
- data/aktuelt_combined.json

Struktur:
{
  "lastUpdated": "...",
  "items": [
    {
      "id": "...",
      "source": "fauske_kommune" | "fauskenf",
      "sourceName": "Fauske kommune" | "Fauske Næringsforum",
      "title": "...",
      "url": "...",
      "image": "...",
      "published": "YYYY-MM-DD" (så langt vi klarer),
      "publishedText": "lesbar dato",
      "ingress": "...",
      "body": "...",       # typisk bare for Fauske kommune-saker
      "category": "...",   # hvis tilgjengelig
      "raw": { ... }       # original item for debugging / fremtidig bruk
    },
    ...
  ]
}
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

KOMMUNE_PATH = DATA_DIR / "nyheter.json"
NF_PATH = DATA_DIR / "fauskenf_nyheter.json"
OUTPUT_PATH = DATA_DIR / "aktuelt_combined.json"


def parse_date_fauskenf(date_str: Optional[str]) -> Optional[str]:
    """
    Fauskenf bruker trolig format 'dd.mm.yyyy'.
    Returnerer ISO 'yyyy-mm-dd' hvis vi klarer det, ellers None.
    """
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
        return dt.date().isoformat()
    except ValueError:
        # fallback hvis det senere blir endret til ISO direkte
        try:
            return datetime.fromisoformat(date_str.strip()).date().isoformat()
        except Exception:
            return None


def parse_date_sortkey(date_str: Optional[str]) -> datetime:
    """
    Gjør publiseringsdato om til noe vi kan sortere på.
    Hvis vi ikke klarer å tolke datoen -> returnerer et "gammelt" tidspunkt.
    """
    if not date_str:
        return datetime.min
    # Prøv ISO først (2025-11-13 eller 2025-11-13T...)
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        pass

    # Prøv kun dato-delen hvis det er 'YYYY-MM-DD'
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except Exception:
        pass

    # Prøv dd.mm.yyyy
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except Exception:
        return datetime.min


def load_kommune_items() -> List[Dict[str, Any]]:
    """
    Leser nyheter fra data/nyheter.json (Fauske kommune) og normaliserer.
    Forventet struktur (fra scraperen din):
    {
      "lastUpdated": "...",
      "items": [
        {
          "title": "...",
          "url": "...",
          "imageUrl": "...",
          "published": "2025-11-13",
          "publishedText": "13. november 2025",
          "ingress": "...",
          "body": "...",
          "bodyHtml": "...",
          "source": "forside-aktuelt-env-card"
        },
        ...
      ]
    }
    """
    if not KOMMUNE_PATH.exists():
        return []

    raw = json.loads(KOMMUNE_PATH.read_text(encoding="utf-8") or "{}")
    items = raw.get("items") or []

    normalized: List[Dict[str, Any]] = []

    for item in items:
        title = item.get("title")
        url = item.get("url")
        image = item.get("imageUrl") or item.get("image")
        published = item.get("published")  # ISO yyyy-mm-dd
        published_text = item.get("publishedText") or published

        # Lag en noenlunde stabil id basert på URL eller tittel
        base_id = url or title or "kommune-unknown"
        base_id = base_id.rstrip("/").rsplit("/", 1)[-1]
        norm_id = "fauske_kommune-" + base_id

        normalized.append(
            {
                "id": norm_id,
                "source": "fauske_kommune",
                "sourceName": "Fauske kommune",
                "title": title,
                "url": url,
                "image": image,
                "published": published,
                "publishedText": published_text,
                "ingress": item.get("ingress"),
                "body": item.get("body"),
                "category": item.get("category"),
                "raw": item,
            }
        )

    return normalized


def load_nf_items() -> List[Dict[str, Any]]:
    """
    Leser nyheter fra data/fauskenf_nyheter.json (Fauske Næringsforum) og normaliserer.

    Forventet struktur (fra scrape_fauskenf_nyheter.py):
    {
      "lastUpdated": "...",
      "items": [
        {
          "id": "fauskenf-2025-11-17-...",
          "source": "fauskenf",
          "sourceName": "Fauske Næringsforum",
          "date": "17.11.2025",
          "title": "...",
          "ingress": "...",
          "category": "...",
          "image": "https://...",
          "url": "https://...",
          "rawText": "..."
        },
        ...
      ]
    }
    """
    if not NF_PATH.exists():
        return []

    raw = json.loads(NF_PATH.read_text(encoding="utf-8") or "{}")
    items = raw.get("items") or []

    normalized: List[Dict[str, Any]] = []

    for item in items:
        title = item.get("title")
        url = item.get("url")
        image = item.get("image")
        date_str = item.get("date")  # dd.mm.yyyy
        iso_date = parse_date_fauskenf(date_str)

        base_id = item.get("id") or url or title or "fauskenf-unknown"
        norm_id = base_id

        normalized.append(
            {
                "id": norm_id,
                "source": "fauskenf",
                "sourceName": "Fauske Næringsforum",
                "title": title,
                "url": url,
                "image": image,
                "published": iso_date,
                "publishedText": date_str,
                "ingress": item.get("ingress"),
                "body": None,  # har vi ikke (enda)
                "category": item.get("category"),
                "raw": item,
            }
        )

    return normalized


def build_combined() -> Dict[str, Any]:
    kommune_items = load_kommune_items()
    nf_items = load_nf_items()

    all_items = kommune_items + nf_items

    # Sorter etter published (nyeste først)
    all_items.sort(
        key=lambda item: parse_date_sortkey(item.get("published")),
        reverse=True,
    )

    return {
        "lastUpdated": datetime.now().isoformat(),
        "items": all_items,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    combined = build_combined()

    OUTPUT_PATH.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"Skrev kombinert Aktuelt-fil med {len(combined.get('items', []))} saker "
        f"til {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()