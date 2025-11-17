#!/usr/bin/env python3
"""
Bygger en kombinert "aktuelt"-fil fra:

- Fauske kommune (data/nyheter.json)
- Fauske Næringsforum (data/fauskenf_nyheter.json)

Output:
  data/aktuelt_combined.json

Felles struktur per item:
{
  "id": "...",
  "source": "fauske_kommune" | "fauskenf",
  "sourceName": "...",
  "title": "...",
  "url": "...",
  "image": "...",
  "published": "YYYY-MM-DD",
  "publishedText": "13. november 2025",
  "ingress": "...",
  "body": "...",
  "category": "...",
  "raw": { ... original data ... }
}
"""

import json
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

FAUSKE_KOMMUNE_PATH = DATA_DIR / "nyheter.json"
FAUSKENF_PATH = DATA_DIR / "fauskenf_nyheter.json"
OUTPUT_PATH = DATA_DIR / "aktuelt_combined.json"


MONTHS_NO = {
    1: "januar",
    2: "februar",
    3: "mars",
    4: "april",
    5: "mai",
    6: "juni",
    7: "juli",
    8: "august",
    9: "september",
    10: "oktober",
    11: "november",
    12: "desember",
}


def to_no_date_text(d: date) -> str:
    """Returnerer dato med norsk månedsnavn, f.eks. '13. november 2025'."""
    return f"{d.day}. {MONTHS_NO[d.month]} {d.year}"


def parse_ddmmyyyy(date_str: str) -> Optional[date]:
    """Parser 'dd.mm.yyyy' til date-objekt."""
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").date()
    except Exception:
        return None


def load_fauske_kommune_items() -> List[Dict[str, Any]]:
    """Leser data fra nyheter.json (Fauske kommune) og normaliserer."""
    if not FAUSKE_KOMMUNE_PATH.exists():
        print(f"ADVARSEL: Fant ikke {FAUSKE_KOMMUNE_PATH}")
        return []

    data = json.loads(FAUSKE_KOMMUNE_PATH.read_text(encoding="utf-8"))
    items = data.get("items", [])

    normalized: List[Dict[str, Any]] = []

    for item in items:
        title = item.get("title") or ""
        url = item.get("url") or ""
        image = item.get("imageUrl") or None

        published_iso = item.get("published")  # forventes 'YYYY-MM-DD'
        published_text = item.get("publishedText") or published_iso or ""

        # id: bruk published + slug fra url hvis mulig
        slug = url.rstrip("/").rsplit("/", 1)[-1] if url else title
        item_id = f"fauske_kommune-{published_iso}-{slug}"

        normalized.append(
            {
                "id": item_id,
                "source": "fauske_kommune",
                "sourceName": "Fauske kommune",
                "title": title,
                "url": url,
                "image": image,
                "published": published_iso,
                "publishedText": published_text,
                "ingress": item.get("ingress") or "",
                "body": item.get("body"),
                "category": None,  # evt. legge til senere om du vil
                "raw": item,
            }
        )

    return normalized


def load_fauskenf_items() -> List[Dict[str, Any]]:
    """Leser data fra fauskenf_nyheter.json (Fauske Næringsforum) og normaliserer."""
    if not FAUSKENF_PATH.exists():
        print(f"ADVARSEL: Fant ikke {FAUSKENF_PATH}")
        return []

    data = json.loads(FAUSKENF_PATH.read_text(encoding="utf-8"))
    items = data.get("items", [])

    normalized: List[Dict[str, Any]] = []

    for item in items:
        raw_id = item.get("id") or ""
        title = item.get("title") or ""
        url = item.get("url") or ""
        image = item.get("image") or None
        raw_date_str = item.get("date") or ""  # 'dd.mm.yyyy' fra scraperen

        d_obj = parse_ddmmyyyy(raw_date_str)
        if d_obj is not None:
            published_iso = d_obj.isoformat()  # 'YYYY-MM-DD'
            published_text = to_no_date_text(d_obj)  # '13. november 2025'
        else:
            # fallback: bruk det vi har
            published_iso = None
            published_text = raw_date_str

        # Ingress: bruk articleBody som ingress (slik du ønsker), evt. fallback
        article_body = item.get("articleBody")
        ingress = article_body or item.get("ingress") or ""
        body = article_body  # inntil vi eventuelt scraper fulltekst senere

        category = item.get("category")

        normalized.append(
            {
                "id": raw_id,
                "source": "fauskenf",
                "sourceName": "Fauske Næringsforum",
                "title": title,
                "url": url,
                "image": image,
                "published": published_iso,
                "publishedText": published_text,
                "ingress": ingress,
                "body": body,
                "category": category,
                "raw": item,
            }
        )

    return normalized


def build_combined() -> Dict[str, Any]:
    """Bygger kombinert aktuelt-listen."""
    kommune_items = load_fauske_kommune_items()
    fauskenf_items = load_fauskenf_items()

    all_items = kommune_items + fauskenf_items

    # Sorter nyeste først på published (ISO). Hvis published mangler, dytt de bakerst.
    def sort_key(it: Dict[str, Any]) -> str:
        p = it.get("published")
        return p or ""

    all_items.sort(key=sort_key, reverse=True)

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "items": all_items,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined = build_combined()

    OUTPUT_PATH.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Skrev {len(combined.get('items', []))} saker til {OUTPUT_PATH}")


if __name__ == "__main__":
    main()