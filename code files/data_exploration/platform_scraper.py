"""Collect cross-platform listing candidates for Bronze ingestion.

This module prepares Booking.com and Vrbo listing data in the exact tabular
shape expected by ``warehouse.py``. The goal is not to build a perfect,
production-grade scraper in one pass; it is to create a repeatable collection
tool that can:

1. Fetch search-result pages directly when requests succeed.
2. Parse saved HTML snapshots when the platforms block automated requests.
3. Write normalized Bronze CSV files that the warehouse can ingest without
   additional manual reshaping.

The parser is intentionally layered and defensive because marketplace markup
changes frequently. Each parser first looks for structured data (JSON-LD,
Next.js state, etc.) and only then falls back to HTML-card extraction.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
BRONZE_RAW_DIR = BASE_DIR / "data" / "bronze" / "raw"
OUTPUT_PATHS = {
    "booking.com": BRONZE_RAW_DIR / "booking" / "listings.csv",
    "vrbo": BRONZE_RAW_DIR / "vrbo" / "listings.csv",
}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
PRICE_PATTERN = re.compile(r"(\d[\d,.\s]*)")
ACCOMMODATES_PATTERN = re.compile(r"(\d+)\s*(?:guest|guests|person|persons|adult|adults)", re.I)
COORDINATE_PATTERN = re.compile(r"-?\d+\.\d+")


@dataclass
class ScrapeRecord:
    """Represent one normalized external-platform listing row.

    The field names match the Bronze template consumed by ``warehouse.py``.
    Keeping this dataclass aligned with the warehouse template means a scrape
    run can feed Gold immediately without a hand-built transformation step.
    """

    platform_listing_id: str
    title: str
    city: str
    neighbourhood_cleansed: str
    neighbourhood_group_cleansed: str
    latitude: float | None
    longitude: float | None
    accommodates: int | None
    price: float | None
    listing_url: str


def parse_args() -> argparse.Namespace:
    """Define the command-line interface for platform scraping."""

    parser = argparse.ArgumentParser(
        description=(
            "Scrape or parse Booking.com / Vrbo search results into the Bronze "
            "cross-platform listing template."
        )
    )
    parser.add_argument(
        "--platform",
        required=True,
        choices=sorted(OUTPUT_PATHS.keys()),
        help="External marketplace to scrape.",
    )
    parser.add_argument(
        "--city",
        required=True,
        help="City label to stamp into the Bronze output, for example 'lisbon'.",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Live search-results URL to fetch. Repeat the flag to collect multiple pages.",
    )
    parser.add_argument(
        "--html-dir",
        type=Path,
        help="Directory with saved HTML files to parse when live requests are blocked.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output CSV. Defaults to the standard Bronze location for the platform.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the output CSV instead of replacing it.",
    )
    parser.add_argument(
        "--neighbourhood-group",
        default="",
        help=(
            "Optional fallback municipality / higher-level area when the platform "
            "page does not expose one clearly."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-request timeout in seconds for live page fetches.",
    )
    return parser.parse_args()


def fetch_html(url: str, timeout: int) -> str:
    """Download one search-results page with a browser-like user agent."""

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def load_html_sources(urls: list[str], html_dir: Path | None, timeout: int) -> list[tuple[str, str]]:
    """Collect HTML content from live URLs and/or saved local files.

    Returning ``(source_label, html_text)`` pairs lets us preserve source
    lineage for debugging without forcing extra columns into the warehouse
    template.
    """

    sources: list[tuple[str, str]] = []

    for url in urls:
        html = fetch_html(url, timeout=timeout)
        sources.append((url, html))

    if html_dir:
        if not html_dir.exists():
            raise FileNotFoundError(f"HTML directory does not exist: {html_dir}")
        for path in sorted(html_dir.glob("*.html")):
            sources.append((str(path), path.read_text(encoding="utf-8", errors="ignore")))

    if not sources:
        raise ValueError("Provide at least one --url or an --html-dir with saved platform HTML.")

    return sources


def clean_text(value: object) -> str:
    """Normalize textual fields into compact warehouse-friendly strings."""

    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_price(value: object) -> float | None:
    """Extract a numeric price from mixed currency/text strings."""

    text = clean_text(value)
    if not text:
        return None

    match = PRICE_PATTERN.search(text.replace("\xa0", " "))
    if not match:
        return None

    numeric = match.group(1).replace(" ", "").replace(",", "")
    try:
        return float(numeric)
    except ValueError:
        return None


def parse_accommodates(value: object) -> int | None:
    """Extract guest capacity from platform snippets when available."""

    text = clean_text(value)
    if not text:
        return None

    match = ACCOMMODATES_PATTERN.search(text)
    if match:
        return int(match.group(1))

    integers = re.findall(r"\d+", text)
    return int(integers[0]) if integers else None


def parse_float(value: object) -> float | None:
    """Safely coerce coordinates or other decimal values."""

    text = clean_text(value)
    if not text:
        return None

    match = COORDINATE_PATTERN.search(text)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def build_record(
    *,
    platform_listing_id: object,
    title: object,
    city: str,
    neighbourhood_cleansed: object = "",
    neighbourhood_group_cleansed: object = "",
    latitude: object = None,
    longitude: object = None,
    accommodates: object = None,
    price: object = None,
    listing_url: object = "",
    base_url: str = "",
    fallback_neighbourhood_group: str = "",
) -> ScrapeRecord | None:
    """Create one normalized Bronze record when enough identifying data exists."""

    listing_id = clean_text(platform_listing_id)
    title_text = clean_text(title)
    url_text = clean_text(listing_url)

    if not listing_id and url_text:
        listing_id = url_text.rstrip("/").split("/")[-1].split("?")[0]

    if not url_text and listing_id and base_url:
        url_text = urljoin(base_url, listing_id)
    elif url_text and base_url:
        url_text = urljoin(base_url, url_text)

    if not listing_id or not title_text or not url_text:
        return None

    return ScrapeRecord(
        platform_listing_id=listing_id,
        title=title_text,
        city=clean_text(city).lower(),
        neighbourhood_cleansed=clean_text(neighbourhood_cleansed),
        neighbourhood_group_cleansed=clean_text(neighbourhood_group_cleansed or fallback_neighbourhood_group),
        latitude=parse_float(latitude),
        longitude=parse_float(longitude),
        accommodates=parse_accommodates(accommodates),
        price=parse_price(price),
        listing_url=url_text,
    )


def extract_id_from_url(url: str) -> str:
    """Derive a stable listing identifier from a marketplace URL when needed."""

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    for key in ["selected", "propertyId", "id"]:
        values = params.get(key)
        if values and values[0]:
            return values[0]

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        return path_parts[-1]

    return url


def walk_objects(value: object) -> Iterable[dict]:
    """Yield every nested dictionary inside a JSON-like object tree."""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for item in value:
            yield from walk_objects(item)


def parse_booking_records(
    html: str,
    city: str,
    fallback_neighbourhood_group: str,
    source_label: str,
) -> list[ScrapeRecord]:
    """Extract Booking.com listings from JSON-LD first, then HTML cards.

    Booking pages often expose hotel results through structured data blocks.
    Those are the most stable source because CSS classes and card markup tend
    to change more frequently than JSON-LD payloads.
    """

    soup = BeautifulSoup(html, "html.parser")
    records: list[ScrapeRecord] = []
    seen_ids: set[str] = set()

    for script in soup.select('script[type="application/ld+json"]'):
        script_text = clean_text(script.string or script.get_text())
        if not script_text:
            continue
        try:
            payload = json.loads(script_text)
        except json.JSONDecodeError:
            continue

        for obj in walk_objects(payload):
            if obj.get("@type") not in {"Hotel", "LodgingBusiness"}:
                continue

            geo = obj.get("geo") or {}
            address = obj.get("address") or {}
            record = build_record(
                platform_listing_id=obj.get("@id") or obj.get("url"),
                title=obj.get("name"),
                city=city,
                neighbourhood_cleansed=address.get("addressLocality") or address.get("addressRegion") or "",
                neighbourhood_group_cleansed=fallback_neighbourhood_group,
                latitude=geo.get("latitude"),
                longitude=geo.get("longitude"),
                price=(obj.get("offers") or {}).get("price"),
                listing_url=obj.get("url"),
                base_url="https://www.booking.com",
                fallback_neighbourhood_group=fallback_neighbourhood_group,
            )
            if record and record.platform_listing_id not in seen_ids:
                seen_ids.add(record.platform_listing_id)
                records.append(record)

    if records:
        return records

    for card in soup.select('[data-testid="property-card"]'):
        title_tag = card.select_one('[data-testid="title"]')
        link_tag = card.select_one("a[href]")
        price_tag = card.select_one('[data-testid="price-and-discounted-price"]') or card.select_one('[data-testid="price"]')
        address_tag = card.select_one('[data-testid="address"]')

        href = link_tag.get("href") if link_tag else ""
        record = build_record(
            platform_listing_id=href,
            title=title_tag.get_text(" ", strip=True) if title_tag else "",
            city=city,
            neighbourhood_cleansed=address_tag.get_text(" ", strip=True) if address_tag else "",
            neighbourhood_group_cleansed=fallback_neighbourhood_group,
            price=price_tag.get_text(" ", strip=True) if price_tag else "",
            listing_url=href,
            base_url="https://www.booking.com",
            fallback_neighbourhood_group=fallback_neighbourhood_group,
        )
        if record and record.platform_listing_id not in seen_ids:
            seen_ids.add(record.platform_listing_id)
            records.append(record)

    if not records:
        raise ValueError(
            f"No Booking.com listings were parsed from {source_label}. "
            "The page markup may have changed or the HTML may be a blocked-response page."
        )

    return records


def parse_vrbo_records(
    html: str,
    city: str,
    fallback_neighbourhood_group: str,
    source_label: str,
) -> list[ScrapeRecord]:
    """Extract Vrbo listings from Next.js state first, then anchor/card fallback."""

    soup = BeautifulSoup(html, "html.parser")
    records: list[ScrapeRecord] = []
    seen_ids: set[str] = set()

    next_data = soup.select_one("script#__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            payload = json.loads(next_data.string)
        except json.JSONDecodeError:
            payload = {}

        for obj in walk_objects(payload):
            candidate_id = obj.get("id") or obj.get("propertyId")
            candidate_url = obj.get("url") or obj.get("landingPageUrl")
            candidate_title = obj.get("name") or obj.get("headline")
            if not candidate_id or not candidate_title or not candidate_url:
                continue

            location = obj.get("location") or obj.get("address") or {}
            coordinates = obj.get("coordinates") or obj.get("geoCoordinates") or {}
            pricing = obj.get("price") or obj.get("priceSummary") or {}
            features = obj.get("features") or obj.get("summary") or ""

            record = build_record(
                platform_listing_id=candidate_id,
                title=candidate_title,
                city=city,
                neighbourhood_cleansed=location.get("neighborhood") or location.get("locality") or "",
                neighbourhood_group_cleansed=fallback_neighbourhood_group,
                latitude=coordinates.get("latitude"),
                longitude=coordinates.get("longitude"),
                accommodates=obj.get("sleeps") or obj.get("maxOccupancy") or features,
                price=pricing.get("amount") or pricing.get("lead") or "",
                listing_url=candidate_url,
                base_url="https://www.vrbo.com",
                fallback_neighbourhood_group=fallback_neighbourhood_group,
            )
            if record and record.platform_listing_id not in seen_ids:
                seen_ids.add(record.platform_listing_id)
                records.append(record)

    if records:
        return records

    for card in soup.select("div.uitk-card.uitk-card-has-link"):
        title_tag = card.select_one("h3:not(.is-visually-hidden)")
        link_tag = card.select_one("a[href*='selected=']")
        if not title_tag or not link_tag:
            continue

        title_text = title_tag.get_text(" ", strip=True)
        location_tag = card.select_one("p.uitk-subheading")
        price_block = card.select_one("[data-test-id='price-summary']") or card
        href = link_tag.get("href", "")

        record = build_record(
            platform_listing_id=extract_id_from_url(href),
            title=title_text,
            city=city,
            neighbourhood_cleansed=location_tag.get_text(" ", strip=True) if location_tag else "",
            neighbourhood_group_cleansed=fallback_neighbourhood_group,
            price=price_block.get_text(" ", strip=True),
            listing_url=href,
            base_url="https://www.vrbo.com",
            fallback_neighbourhood_group=fallback_neighbourhood_group,
        )
        if record and record.platform_listing_id not in seen_ids:
            seen_ids.add(record.platform_listing_id)
            records.append(record)

    if not records:
        raise ValueError(
            f"No Vrbo listings were parsed from {source_label}. "
            "The page markup may have changed or the HTML may be a blocked-response page."
        )

    return records


def parse_sources(
    platform: str,
    sources: list[tuple[str, str]],
    city: str,
    fallback_neighbourhood_group: str,
) -> list[ScrapeRecord]:
    """Parse every HTML source with the platform-specific extractor."""

    parser = parse_booking_records if platform == "booking.com" else parse_vrbo_records
    records: list[ScrapeRecord] = []

    for source_label, html in sources:
        records.extend(parser(html, city, fallback_neighbourhood_group, source_label))

    # Deduplicate after parsing so repeated pages or overlapping searches do not
    # create multiple Bronze rows for the same external listing.
    unique: dict[str, ScrapeRecord] = {}
    for record in records:
        unique[record.platform_listing_id] = record
    return list(unique.values())


def write_output(records: list[ScrapeRecord], output_path: Path, append: bool) -> None:
    """Persist the scraped data in the Bronze CSV format expected by Gold."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([asdict(record) for record in records])

    if append and output_path.exists():
        existing = pd.read_csv(output_path)
        frame = pd.concat([existing, frame], ignore_index=True)
        frame = frame.drop_duplicates(subset=["platform_listing_id"], keep="last")

    frame = frame.sort_values(by=["city", "platform_listing_id"]).reset_index(drop=True)
    frame.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)


def main() -> None:
    """Run a scrape/parse job and materialize Bronze cross-platform listings."""

    args = parse_args()
    output_path = args.output or OUTPUT_PATHS[args.platform]
    sources = load_html_sources(args.url, args.html_dir, timeout=args.timeout)
    records = parse_sources(
        platform=args.platform,
        sources=sources,
        city=args.city,
        fallback_neighbourhood_group=args.neighbourhood_group,
    )
    write_output(records, output_path=output_path, append=args.append)

    print(
        f"Wrote {len(records)} {args.platform} listings to {output_path}"
    )


if __name__ == "__main__":
    main()
