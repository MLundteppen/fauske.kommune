#!/usr/bin/env python3
"""
Scraper nyheter fra Fauske Næringsforum:

Kilde:
    https://www.fauskenf.no/liste-nyheter-alle-nyheter

Lagrer til:
    data/fauskenf_nyheter.json

Struktur i output:
{
  "lastUpdated": "...",
  "items": [
    {
      "id": "fauskenf-2025-11-17-lokal-kompetanseheving-...",
      "source": "fauskenf",
      "sourceName": "Fauske Næringsforum",
      "date": "17.11.2025",
      "title": "Lokal kompetanseheving og gode utdanningsløp - helt nødvendig for vårt arbeidsliv!",
      "ingress": "Gjennom året representerer Fauske Næringsforum i både regionale kompetanseforumet ...",
      "category": "Kompetanse, utdanning og rekruttering",
      "image": "https://www.fauskenf.no/path/til/bilde.jpg",
      "url": "https://www.fauskenf.no/nyheter-alle-nyheter/slug-1234",
      "rawText": "17.11.2025 ... (hele teksten fra kortet)",
    },
    ...
  ]
}
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fauskenf.no"
LIST_URL = "https://www.fauskenf.no/liste-nyheter-alle-nyheter"

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_PATH = DATA_DIR / "fauskenf_nyheter.json"

USER_AGENT = "FauskeKommuneAppScraper/1.0 (+kontakt Fauske kommune / Lundteppen Media)"


def make_absolute_url(href: str) -> str:
    """Gjør relative lenker om til absolute."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return f"{BASE_URL}/{href}"


def extract_items_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Parser HTML fra /liste-nyheter-alle-nyheter og henter ut alle nyhetskortene.

    Strategi:
      - Finn alle <a>-elementer som har href og tekst som starter med dato "dd.mm.yyyy".
      - I hvert kort:
          * date  = dd.mm.yyyy
          * title = tittel (prøves hentet fra h2/h3, ellers brukes resten av teksten)
          * ingress = første <p> eller del av teksten etter tittel (best-effort)
          * category = siste "tag" hvis vi finner egen tag, ellers None
          * image = første <img> i kortet, hvis finnes
    """
    soup = BeautifulSoup(html, "html.parser")

    # Prøv å begrense oss til hovedinnhold for å unngå meny / footer
    main = soup.find("main") or soup

    items: List[Dict[str, Any]] = []

    # Regex for å finne dato i begynnelsen av teksten
    date_pattern = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(.*)$")

    for a in main.find_all("a", href=True):
        # Hent all tekst i kortet
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            continue

        m = date_pattern.match(text)
        if not m:
            # Ikke et nyhetskort (mangler dato i starten)
            continue

        date_str = m.group(1)
        rest = m.group(2)  # tittel + ingress + kategori i én string (fallback)

        # Prøv å plukke ut mer strukturert info basert på under-tags
        title: Optional[str] = None
        ingress: Optional[str] = None
        category: Optional[str] = None

        # Tittel: typisk i h2/h3/h4
        header = a.find(["h2", "h3", "h4"])
        if header:
            title = header.get_text(" ", strip=True)

        # Ingress: første <p> i kortet
        p = a.find("p")
        if p:
            ingress = p.get_text(" ", strip=True)

        # Kategori: ofte en egen "tag"-span
        # (Vi gjetter litt her – du kan justere class-søk når du ser HTML-en i DevTools)
        cat_el = a.find(
            ["span", "div"],
            class_=lambda c: c
            and any(
                token.lower() in {"kategori", "category", "tag"}
                for token in c.split()
            ),
        )
        if cat_el:
            category = cat_el.get_text(" ", strip=True)

        # Ingress på listesiden ligger i et <article class="text-article"> rett under overskriften.
        # Prøv å finne denne ved å gå opp til et felles "kort"-element og lete der.
        card_root = a
        article_ingress = None
        while card_root is not None:
            article_el = card_root.find(
                "article",
                class_=lambda c: c and "text-article" in c,
            )
            if article_el is not None:
                article_ingress = article_el.get_text(" ", strip=True)
                break
            card_root = card_root.parent

        if article_ingress:
            ingress = article_ingress

        # Fallback om vi ikke fant tittel/ingress strukturert:
        if title is None:
            # Bruk hele rest som tittel
            title = rest
        if ingress is None:
            # Ingress kan vi la være tom i første versjon – vi har fortsatt rawText
            ingress = ""

        # Bilde: første <img> i kortet
        image_url: Optional[str] = None
        img = a.find("img")
        if img and img.get("src"):
            image_url = make_absolute_url(img["src"])

        url = make_absolute_url(a["href"])

        # Lag en nokså unik id basert på dato + URL-slug
        slug_part = url.rstrip("/").rsplit("/", 1)[-1]
        item_id = f"fauskenf-{date_str}-{slug_part}"

        items.append(
            {
                "id": item_id,
                "source": "fauskenf",
                "sourceName": "Fauske Næringsforum",
                "date": date_str,
                "title": title,
                "ingress": ingress,
                "category": category,
                "image": image_url,
                "url": url,
                "rawText": text,
            }
        )

    return items


def extract_article_text(html: str) -> Dict[str, Optional[str]]:
    """
    Henter ut ingress/tekst fra selve artikkelsiden.

    Vi ser etter:
      <article class="text-article"> ... </article>

    Returnerer både ren tekst og rå HTML-strengen, slik at appen senere
    kan velge om den vil vise formatert tekst eller kun plain text.
    """
    soup = BeautifulSoup(html, "html.parser")

    article = soup.find(
        "article",
        class_=lambda c: c and "text-article" in c,
    )
    if not article:
        return {"articleBody": None, "articleHtml": None}

    # Ren tekst (med linjeskift)
    body_text = article.get_text("\n", strip=True)
    # HTML-streng for hele artikkelen
    body_html = str(article)

    return {
        "articleBody": body_text,
        "articleHtml": body_html,
    }


def scrape_fauskenf_nyheter() -> Dict[str, Any]:
    """
    Henter HTML fra nyhetssiden og returnerer strukturert JSON-klar dict.

    Steg:
      1) Hent liste-siden med alle nyhetskortene.
      2) Ekstraher kort-info (dato, tittel, ingress, bilde, lenke).
      3) For hver sak: gå inn på artikkelsiden og hent
         <article class="text-article"> som er selve ingressen/teksten.
    """
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(LIST_URL, headers=headers, timeout=30)
    resp.raise_for_status()

    items = extract_items_from_html(resp.text)

    # Hent detaljer for hver artikkel
    for item in items:
        url = item.get("url")
        if not url:
            continue

        try:
            detail_resp = requests.get(url, headers=headers, timeout=30)
            detail_resp.raise_for_status()
            details = extract_article_text(detail_resp.text)
            item["articleBody"] = details.get("articleBody")
            item["articleHtml"] = details.get("articleHtml")
        except Exception as e:
            # Ikke stopp hele scraperen om én artikkel feiler
            print(f"ADVARSEL: Klarte ikke hente artikkel for {url}: {e}")
            item["articleBody"] = None
            item["articleHtml"] = None

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Henter nyheter fra {LIST_URL} ...")
    data = scrape_fauskenf_nyheter()

    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"Skrev {len(data.get('items', []))} nyheter til {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()