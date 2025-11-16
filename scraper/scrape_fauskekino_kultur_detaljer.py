#!/usr/bin/env python3
"""
Leser data/kultur_program.json og henter detaljer for hvert kulturarrangement
fra HTML-sidene på fauskekino.no.

Resultatet lagres i:
    data/kultur_detaljer.json

Per arrangement:
- id
- title
- url
- body: renset brødtekst (fra RichText_StyledRichText__ttWfr)
- images: liste med bilde-URL-er (inkl. hovedbilde, men uten Sanity-logoen)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fauskekino.no"

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
PROGRAM_PATH = DATA_DIR / "kultur_program.json"
DETAILS_PATH = DATA_DIR / "kultur_detaljer.json"

USER_AGENT = "FauskeKulturScraper/1.0 (+https://www.fauskekino.no)"


def load_kultur_program() -> Dict[str, Any]:
    """
    Leser det forenklede kulturprogrammet:
    {
      "lastUpdated": "...",
      "events": [ { id, title, url, shows: [...] }, ... ]
    }
    """
    if not PROGRAM_PATH.exists():
        raise FileNotFoundError(
            f"{PROGRAM_PATH} finnes ikke. Kjør først scrape_fauskekino_kultur.py"
        )

    text = PROGRAM_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(
            f"{PROGRAM_PATH} er tom. Kjør først scrape_fauskekino_kultur.py"
        )

    return json.loads(text)


def make_absolute_url(src: str) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("/"):
        return BASE_URL + src
    return BASE_URL + "/" + src


def extract_main_text_and_images(html: str, title: Optional[str]) -> Dict[str, Any]:
    """
    Henter ut brødtekst og bilder for kulturarrangement.

    Prioritet:
    1) Bruk <div class="...RichText_StyledRichText__ttWfr...">  (dette er info-teksten)
       - body = alle <p> inni denne div-en
       - images = alle <img> inni denne div-en (uten logo)
       - + hovedbilde med class Kulturarrangement_SArticleImage__ygV3q
    2) Hvis den ikke finnes, faller vi tilbake til main/article/body,
       men filtrerer fortsatt bort logo-bildet.
    """
    soup = BeautifulSoup(html, "html.parser")

    def is_logo_url(url: str) -> bool:
        # Spesifikk Sanity-logo vi vil droppe
        if "f63100c14d5183e3d3132f62b46573e55e131fa2-373x90.svg" in url:
            return True
        # Generelt: dropp .svg-logoer fra sanity
        if "cdn.sanity.io/images/ilasalev/production" in url and url.endswith(".svg"):
            return True
        return False

    images: List[str] = []

    # Helper for å legge til hovedbildet med Kulturarrangement_SArticleImage__ygV3q
    def collect_main_article_images():
        nodes = soup.find_all(
            class_=lambda c: c and "Kulturarrangement_SArticleImage__ygV3q" in c
        )
        for node in nodes:
            if node.name == "img":
                candidate = node
            else:
                candidate = node.find("img")
            if not candidate:
                continue
            src = candidate.get("src")
            if not src:
                continue
            full = make_absolute_url(src)
            if is_logo_url(full):
                continue
            if full not in images:
                images.append(full)

    # 1) Forsøk å finne selve riktekst-boksen
    rich_div = soup.find(
        "div",
        class_=lambda c: c and "RichText_StyledRichText__ttWfr" in c,
    )

    if rich_div:
        # --- Tekst: alle <p> inne i riktekst-boksen ---
        paragraphs = []
        for p in rich_div.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if txt:
                paragraphs.append(txt)
        body = "\n\n".join(paragraphs).strip()

        # --- Bilder: alle <img> inne i riktekst-boksen ---
        for img in rich_div.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            full = make_absolute_url(src)
            if is_logo_url(full):
                continue
            if full not in images:
                images.append(full)

        # --- Hovedbilde(r) med Kulturarrangement_SArticleImage__ygV3q ---
        collect_main_article_images()

        return {"body": body, "images": images}

    # 2) Fallback hvis vi ikke finner riktekst-div: bruk main/article/body
    main_el = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", attrs={"role": "main"})
        or soup.body
        or soup
    )

    for img in main_el.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        full = make_absolute_url(src)
        if is_logo_url(full):
            continue
        if full not in images:
            images.append(full)

    # I fallback-modus tar vi fortsatt med hovedbilde(r)
    collect_main_article_images()

    text = main_el.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    stop_markers = [
        "KONTAKT",
        "Kontakt",
        "ADRESSE",
        "Adresse",
        "BILLETTKJØP",
        "Billettkjøp",
        "Nettsiden er utviklet av Filmweb.",
    ]

    cut_index = None
    for i, line in enumerate(lines):
        if any(line.startswith(marker) for marker in stop_markers):
            cut_index = i
            break

    if cut_index is not None:
        lines = lines[:cut_index]

    # Fjern tittel-tekst hvis den står øverst
    if title and lines and lines[0] == title.strip():
        lines = lines[1:]

    body = "\n\n".join(lines).strip()

    return {"body": body, "images": images}


def fetch_event_details(url: str, title: Optional[str]) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return extract_main_text_and_images(resp.text, title)


def build_kultur_details(program_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Går gjennom alle events i kultur_program.json og henter HTML-detaljer.
    """
    events = program_data.get("events") or []
    print(f"Fant {len(events)} kultur-arrangement i kultur_program.json.")

    results: List[Dict[str, Any]] = []

    for idx, ev in enumerate(events):
        ev_id = ev.get("id")
        title = ev.get("title")
        url = ev.get("url") or (
            f"{BASE_URL}/kulturprogram/{ev_id}" if ev_id else None
        )

        print(f"[{idx+1}/{len(events)}] {title}  (id={ev_id}, url={url})")

        if not url:
            print("  ADVARSEL: Ingen URL for dette arrangementet. Hopper over.")
            continue

        try:
            details = fetch_event_details(url, title)
        except Exception as e:
            print(f"  FEIL ved henting av {url}: {e}")
            continue

        results.append(
            {
                "id": ev_id,
                "title": title,
                "url": url,
                "body": details.get("body", ""),
                "images": details.get("images", []),
            }
        )

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "events": results,
    }


def main() -> None:
    print(f"Leser kulturprogram fra {PROGRAM_PATH} ...")
    program_data = load_kultur_program()

    print("Henter detaljer for hvert kulturarrangement ...")
    details = build_kultur_details(program_data)

    DETAILS_PATH.write_text(
        json.dumps(details, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"Skrev detaljer for {len(details.get('events', []))} arrangement "
        f"til {DETAILS_PATH}"
    )


if __name__ == "__main__":
    main()