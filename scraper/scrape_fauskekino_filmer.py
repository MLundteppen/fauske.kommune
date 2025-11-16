#!/usr/bin/env python3
"""
Leser data/fauskekino_program_raw.json (fra scrape_fauskekino_program.py)
og bygger en egen film-liste med detaljer fra filmwebMovies:

- tittel, originaltittel
- aldersgrense + begrunnelse
- spilletid
- nasjonalitet, språk, sjangre
- ingress + hovedtekst (fra Sanity-blocks)
- plakat-URL
- stillbilder
- trailer-ID-er

Kjør:
    cd /Users/fauskekino/Documents/fauske.kommune/scraper
    python3 scrape_fauskekino_filmer.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
PROGRAM_RAW_PATH = DATA_DIR / "fauskekino_program_raw.json"
FILMS_OUT_PATH = DATA_DIR / "fauskekino_filmer.json"


def load_program_raw() -> Dict[str, Any]:
    """
    Leser fauskekino_program_raw.json og returnerer innholdet.
    Forventer struktur:
    {
      "lastUpdated": "...",
      "raw": {
        "movies": [...],
        "filmwebMovies": { "EDI...": {...}, ... }
      }
    }
    """
    if not PROGRAM_RAW_PATH.exists():
        raise FileNotFoundError(
            f"{PROGRAM_RAW_PATH} finnes ikke. Kjør først scrape_fauskekino_program.py"
        )

    text = PROGRAM_RAW_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(
            f"{PROGRAM_RAW_PATH} er tom. Kjør først scrape_fauskekino_program.py"
        )

    data = json.loads(text)
    return data


def blocks_to_plaintext(blocks: Optional[List[Dict[str, Any]]]) -> str:
    """
    Konverterer Sanity-blocks (bodyText / ingress) til enkel tekst.
    """
    if not blocks:
        return ""

    parts: List[str] = []
    for block in blocks:
        if block.get("_type") != "block":
            continue
        children = block.get("children") or []
        text = "".join(
            child.get("text", "")
            for child in children
            if child.get("_type") == "span"
        )
        if text.strip():
            parts.append(text.strip())

    return "\n\n".join(parts)


def first_image_url(images: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """
    Returnerer første image.asset.url fra en liste med imagesV2/postersV2/etc.
    """
    if not images:
        return None

    for img in images:
        asset = img.get("asset") or {}
        url = asset.get("url")
        if url:
            return url

    return None


def collect_image_urls(images: Optional[List[Dict[str, Any]]]) -> List[str]:
    """
    Samler alle image.asset.url-ene fra en liste med imagesV2 / imagesOverrideV2.
    """
    urls: List[str] = []
    if not images:
        return urls

    for img in images:
        asset = img.get("asset") or {}
        url = asset.get("url")
        if url:
            urls.append(url)
    return urls


def build_films_from_program(program_raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lager en liste med filmer ved å matche:
    - raw.movies[*].mainVersionId  (EDI-ID)
    med
    - raw.filmwebMovies[EDI-ID]
    """
    raw = program_raw.get("raw", program_raw)  # fallback om "raw" ikke finnes
    movies = raw.get("movies", [])
    filmweb_map: Dict[str, Dict[str, Any]] = raw.get("filmwebMovies", {})

    films_out: List[Dict[str, Any]] = []

    for movie in movies:
        movie_id = movie.get("mainVersionId") or movie.get("mainVersionEDI")
        title = movie.get("title")

        if not movie_id:
            print(f"  ADVARSEL: Fant ingen mainVersionId for film '{title}'. Hopper over.")
            continue

        fw = filmweb_map.get(movie_id)
        if not fw:
            # Kan være at noen filmer i programmet ikke har filmweb-data (f.eks. lokale arrangement)
            print(f"  ADVARSEL: Ingen filmwebMovies-oppføring for {movie_id} ({title}).")
            continue

        age = ""
        age_reason = ""
        recommended_age = ""
        age_info = fw.get("ageRating") or {}
        if isinstance(age_info, dict):
            age = age_info.get("age", "") or ""
            age_reason = age_info.get("ageReason", "") or ""
            recommended_age = age_info.get("recommendedAge", "") or ""

        ingress_text = blocks_to_plaintext(fw.get("ingress"))
        body_text = blocks_to_plaintext(fw.get("bodyText"))

        poster_url = (
            first_image_url(fw.get("postersV2"))
            or first_image_url(fw.get("imagesOverrideV2"))
            or first_image_url(fw.get("imagesV2"))
        )

        stills = []
        stills.extend(collect_image_urls(fw.get("imagesV2")))
        stills.extend(collect_image_urls(fw.get("imagesOverrideV2")))

        trailers = [
            t.get("videoId")
            for t in (fw.get("trailers") or [])
            if t.get("videoId")
        ]

        film_obj = {
            # Primær-ID (samme som EDI / mainVersionId)
            "id": movie_id,

            # Titler
            "title": fw.get("title") or title,
            "originalTitle": fw.get("originalTitle") or "",

            # Aldersgrenser
            "age": age,
            "ageReason": age_reason,
            "recommendedAge": recommended_age,

            # Spilletid osv
            "runningTime": fw.get("runningTime") or "",
            "nationality": fw.get("nationality") or [],
            "originalLanguage": fw.get("originalLanguage") or [],
            "genres": fw.get("genres") or [],

            # Personer / distributør
            "cast": fw.get("castV2") or "",
            "director": fw.get("directorV2") or "",
            "distributor": (fw.get("distributor") or {}).get("name", ""),

            # Tekster
            "ingress": ingress_text,
            "description": body_text,
            "oneliner": fw.get("oneliner") or "",

            # Bilder
            "posterUrl": poster_url,
            "stills": stills,

            # Trailer(e)
            "trailers": trailers,

            # Diverse flagg
            "isKinoklubb": fw.get("isKinoklubb") or False,

            # Litt info fra program-delen (fint å ha i appen)
            "programTitle": title,
            "programSlug": movie.get("url"),
            "movieType": movie.get("movieType"),
        }

        films_out.append(film_obj)

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "films": films_out,
    }


def main() -> None:
    print(f"Leser programrådata fra {PROGRAM_RAW_PATH} ...")
    program_raw = load_program_raw()

    films_data = build_films_from_program(program_raw)

    FILMS_OUT_PATH.write_text(
        json.dumps(films_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"Skrev detaljer for {len(films_data.get('films', []))} filmer til "
        f"{FILMS_OUT_PATH}"
    )


if __name__ == "__main__":
    main()