import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fauske.kommune.no"
START_URL = BASE_URL + "/"

NORWEGIAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "mars": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}


def parse_date(date_str: str) -> Optional[str]:
    """
    Prøver å tolke dato fra tekst som f.eks:
    - '13. november 2025'
    - '13. november 2025 kl. 18:00'
    Returnerer ISO-dato '2025-11-13' eller None hvis parsing feiler.
    """
    if not date_str:
        return None

    parts = date_str.strip().split()
    if len(parts) < 3:
        return None

    # Vi bruker de tre første delene: dag, måned, år
    day_part, month_part, year_part = parts[0], parts[1], parts[2]
    day_part = day_part.rstrip(".")

    try:
        day = int(day_part)
        year = int(year_part)
        month = NORWEGIAN_MONTHS.get(month_part.lower())
        if not month:
            return None
        dt = datetime(year, month, day)
        return dt.date().isoformat()
    except Exception:
        return None


def class_has(fragment: str):
    """
    Helper for å matche class-attributter som inneholder et fragment.
    Brukes som: class_=class_has("env-text-p")
    """
    def matcher(c):
        if not c:
            return False
        if isinstance(c, str):
            return fragment in c
        # c kan være en liste med klassenavn
        return any(fragment in cls for cls in c)
    return matcher


def get_article_content(url: str, title: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Henter innholdet fra en artikkel-side.
    Returnerer (body_html, body_text):

    - body_html: HTML med struktur (h2, p, li, a, osv.) fra selve artikkelteksten
    - body_text: ren tekst-versjon av det samme
    """
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "FauskeAppScraper/1.0 (+https://www.fauske.kommune.no)"},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[ADVARSEL] Klarte ikke å hente artikkel {url}: {e}")
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main") or soup

    article_container = None

    # 1: Prøv først å finne blokka etter <div id="Innhold">, med class "sv-text-portlet-content"
    innhold_marker = main.find("div", id="Innhold")
    if innhold_marker:
        candidate = innhold_marker.find_next(
            "div",
            class_=lambda c: c and "sv-text-portlet-content" in c
        )
        if candidate:
            article_container = candidate

    # 2: Fallback hvis strukturen er annerledes
    if article_container is None:
        article_container = (
            main.find(class_=class_has("env-text-content"))
            or main.find("article")
            or main
        )

    # 3: Fjern footer / evalueringsblokker med disse tekstene
    bad_markers = [
        "Fant du det du var på jakt etter",
        "Sist oppdatert",
    ]
    for marker in bad_markers:
        node = article_container.find(string=lambda s: s and marker in s)
        if node:
            parent = node.find_parent()
            if parent and parent is not article_container:
                parent.decompose()
            else:
                node.extract()

    # 4: Bygg HTML (innerHTML av containeren)
    body_html = article_container.decode_contents().strip()
    if not body_html:
        body_html = None

    # 5: Bygg ren tekst
    raw_text = article_container.get_text("\n", strip=True)

    # For sikkerhets skyld: klipp bort alt etter "Sist oppdatert" / feedback hvis noe gjenstår
    for marker in bad_markers:
        idx = raw_text.find(marker)
        if idx != -1:
            raw_text = raw_text[:idx].rstrip()
            break

    lines = [ln.strip() for ln in raw_text.split("\n")]
    cleaned_lines = [ln for ln in lines if ln]
    body_text = "\n".join(cleaned_lines).strip() or None

    return body_html, body_text


def scrape_aktuelt_items():
    resp = requests.get(
        START_URL,
        headers={"User-Agent": "FauskeAppScraper/1.0 (+https://www.fauske.kommune.no)"},
        timeout=10,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    items = []

    # Alle kort: <li class="env-list__item env-card">
    cards = soup.select("li.env-list__item.env-card")
    print(f"Fant {len(cards)} env-card-elementer på forsiden.")

    for li in cards:
        # 1) Lenke til saken: <a ... class="... env-card__body ...">
        link_tag = li.find("a", class_=class_has("env-card__body"))
        if not link_tag or not link_tag.get("href"):
            continue

        href = link_tag["href"].strip()
        if href.startswith("/"):
            url = BASE_URL + href
        else:
            url = href

        # 2) Bilde: første <img> inni kortet
        img_tag = li.find("img", src=True)
        image_url: Optional[str] = None
        if img_tag:
            src = img_tag["src"].strip()
            if src.startswith("/"):
                image_url = BASE_URL + src
            else:
                image_url = src

        # 3) Dato/tid: <p class="... env-text-p ...">
        date_p = li.find("p", class_=class_has("env-text-p"))
        published_text = date_p.get_text(strip=True) if date_p else None
        published_iso = parse_date(published_text) if published_text else None

        # 4) Tittel: <h3 class="... env-ui-text-sectionheading ...">
        title_h3 = li.find("h3", class_=class_has("env-ui-text-sectionheading"))
        title = title_h3.get_text(strip=True) if title_h3 else "(uten tittel)"

        # 5) Ingress: <div class="... env-text-p ...">
        ingress_div = li.find("div", class_=class_has("env-text-p"))
        ingress = ingress_div.get_text(strip=True) if ingress_div else None

        # 6) Fullt innhold fra artikkelsiden (HTML + plain text)
        body_html, body_text = get_article_content(url, title)

        items.append(
            {
                "title": title,
                "url": url,
                "imageUrl": image_url,
                "published": published_iso,
                "publishedText": published_text,
                "ingress": ingress,
                "body": body_text,      # ren tekst
                "bodyHtml": body_html,  # HTML med h2/p/li/a osv. bevart
                "source": "forside-aktuelt-env-card",
            }
        )

    return items


def save_to_json(items):
    # Finn ../data/nyheter.json relativt til denne fila
    output_path = Path(__file__).resolve().parent.parent / "data" / "nyheter.json"

    data = {
        "lastUpdated": datetime.now().isoformat(),
        "items": items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Skrev {len(items)} artikler til {output_path}")


def main():
    items = scrape_aktuelt_items()
    save_to_json(items)


if __name__ == "__main__":
    main()