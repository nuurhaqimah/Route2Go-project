"""
external_pois.py
Fetches real tourist destinations from OpenStreetMap via the Overpass API,
and ranks them using Wikipedia pageviews as a free popularity signal.

Why these two sources:
  - Overpass needs no API key and no signup, and OSM data is ODbL licensed,
    which explicitly permits caching results in our own database. Paid
    providers (Google Places, Foursquare) restrict caching, which is the
    thing that keeps this free.
  - No free provider exposes user reviews or star ratings. Wikipedia
    pageviews are a validated stand-in for real visitor numbers, so we use
    them to rank rather than inventing a rating.

Results are normalised to the same shape as rows in the `poi` table so they
can be cached there alongside hand-curated entries.
"""
import datetime
import time
import urllib.parse

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "{wiki}/all-access/user/{article}/daily/{start}/{end}"
)

# Overpass is a free, shared, donation-funded service. Identify ourselves and
# keep request volume low so we stay a good citizen. It answers 429 when we are
# querying too fast and 504 when a query is too heavy for the current load, so
# both are retried with a growing delay rather than treated as fatal.
USER_AGENT = "Route2Go/1.0 (weekend itinerary planner; local development)"
REQUEST_PAUSE_SECONDS = 5
RETRY_STATUSES = (429, 504)
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 15

# Maps Route2Go's four categories onto OSM tag selectors. Each entry is a
# list of raw Overpass filters applied to both nodes and ways.
CATEGORY_TAGS = {
    "history": [
        '["historic"]',
        '["tourism"="museum"]',
        '["amenity"="place_of_worship"]["heritage"]',
    ],
    "nature": [
        '["leisure"~"^(park|garden|nature_reserve)$"]',
        '["natural"~"^(beach|peak|waterfall|cave_entrance)$"]',
        '["tourism"~"^(viewpoint|zoo)$"]',
    ],
    "food": [
        '["amenity"~"^(restaurant|cafe|food_court)$"]',
    ],
    "shopping": [
        '["shop"~"^(mall|department_store)$"]',
        '["amenity"="marketplace"]',
    ],
}

# OSM marks defunct places by prefixing tags rather than deleting the object.
# Skipping these is the main defence against recommending a closed business.
CLOSED_PREFIXES = ("disused:", "abandoned:", "razed:", "demolished:", "removed:")


def _is_closed(tags):
    """True if OSM signals this place is no longer operating."""
    if any(k.startswith(CLOSED_PREFIXES) for k in tags):
        return True
    if tags.get("opening_hours", "").strip().lower() in {"closed", "off"}:
        return True
    return False


def _build_query(city, category, limit):
    """Overpass QL selecting POIs of one category inside a named area."""
    selectors = CATEGORY_TAGS[category]
    parts = []
    for sel in selectors:
        parts.append(f"  node{sel}(area.searchArea);")
        parts.append(f"  way{sel}(area.searchArea);")
    body = "\n".join(parts)
    # "out tags center" gives tags plus a single representative coordinate,
    # which works for ways (polygons) as well as nodes.
    return (
        f'[out:json][timeout:90];\n'
        f'area["name"="{city}"]->.searchArea;\n'
        f'(\n{body}\n);\n'
        f'out tags center {limit};'
    )


def fetch_city_pois(city, country, category, limit=40, session=None):
    """
    Fetch POIs of one category for one city.

    Returns a list of dicts shaped like `poi` rows. budget_level and
    travel_style are left None: OSM carries no reliable equivalent, and
    guessing them would pollute the curated data.
    """
    if category not in CATEGORY_TAGS:
        raise ValueError(f"unknown category: {category}")

    http = session or requests
    query = _build_query(city, category, limit)

    for attempt in range(MAX_RETRIES):
        resp = http.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=180,
        )
        if resp.status_code in RETRY_STATUSES and attempt < MAX_RETRIES - 1:
            delay = RETRY_BACKOFF_SECONDS * (attempt + 1)
            print(f"  [{city}/{category}] {resp.status_code} from Overpass, "
                  f"retrying in {delay}s")
            time.sleep(delay)
            continue
        resp.raise_for_status()
        break

    out = []
    seen = set()
    for el in resp.json().get("elements", []):
        tags = el.get("tags", {})
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        if not name or _is_closed(tags):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)

        center = el.get("center") or {}
        out.append({
            "name": name,
            "category": category,
            "description": _describe(tags, city),
            "location": city,
            "country": country,
            "budget_level": None,
            "travel_style": None,
            "source": "osm",
            "external_id": f"osm:{el['type']}/{el['id']}",
            "lat": el.get("lat", center.get("lat")),
            "lon": el.get("lon", center.get("lon")),
            "wikipedia": tags.get("wikipedia"),
        })
    return out


def _describe(tags, city):
    """Build a short human description from whatever tags OSM provides."""
    if tags.get("description"):
        return tags["description"].strip()

    kind = (
        tags.get("tourism")
        or tags.get("historic")
        or tags.get("leisure")
        or tags.get("natural")
        or tags.get("shop")
        or tags.get("amenity")
        or "place"
    ).replace("_", " ")

    text = f"{kind.capitalize()} in {city}."
    if tags.get("cuisine"):
        text += f" Cuisine: {tags['cuisine'].replace('_', ', ')}."
    if tags.get("opening_hours"):
        text += f" Hours: {tags['opening_hours']}."
    return text


def pageviews(wikipedia_tag, days=90, session=None):
    """
    Total pageviews over the last `days` for an OSM `wikipedia` tag such as
    "en:Brunei Museum". Returns None when the tag is missing or the article
    has no data — callers should treat None as "unranked", not zero.
    """
    if not wikipedia_tag or ":" not in wikipedia_tag:
        return None
    lang, _, article = wikipedia_tag.partition(":")
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    url = PAGEVIEWS_URL.format(
        wiki=f"{lang}.wikipedia",
        article=urllib.parse.quote(article.replace(" ", "_"), safe=""),
        start=f"{start:%Y%m%d}",
        end=f"{end:%Y%m%d}",
    )
    http = session or requests
    try:
        resp = http.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.status_code != 200:
            return None
        return sum(item.get("views", 0) for item in resp.json().get("items", []))
    except requests.RequestException:
        return None


def fetch_city(city, country, categories=None, limit=40, with_popularity=True):
    """
    Fetch every category for one city, attaching popularity where available.
    Pauses between requests to stay within Overpass's fair-use expectations.
    """
    categories = categories or list(CATEGORY_TAGS)
    results = []
    with requests.Session() as session:
        for i, category in enumerate(categories):
            if i:
                time.sleep(REQUEST_PAUSE_SECONDS)
            try:
                found = fetch_city_pois(city, country, category, limit, session)
            except requests.RequestException as e:
                print(f"  [{city}/{category}] fetch failed: {e}")
                continue
            print(f"  [{city}/{category}] {len(found)} places")
            results.extend(found)

        if with_popularity:
            for poi in results:
                if poi.get("wikipedia"):
                    poi["popularity"] = pageviews(poi["wikipedia"], session=session)
    return results
