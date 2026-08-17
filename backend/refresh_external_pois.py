"""
refresh_external_pois.py
Populates the `poi` table with real destinations fetched from OpenStreetMap,
ranked by Wikipedia pageviews.

Curated rows (source='local') are never modified — external places that share a
name with a curated entry are skipped, so hand-written "local secret" entries
always win.

Usage:
    python refresh_external_pois.py                       # every curated city
    python refresh_external_pois.py --city "Kuala Lumpur" --country Malaysia
    python refresh_external_pois.py --country Brunei
    python refresh_external_pois.py --limit 20 --no-popularity
    python refresh_external_pois.py --stale-days 30       # skip fresh cities

Safe to re-run: rows are upserted on external_id, not duplicated.
"""
import argparse
import sys
import time
from datetime import datetime

import database
import external_pois


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--city", help="single city to refresh (requires --country)")
    p.add_argument("--country", help="restrict to one country")
    p.add_argument("--limit", type=int, default=40,
                   help="max places per category per city (default 40)")
    p.add_argument("--no-popularity", action="store_true",
                   help="skip Wikipedia pageview lookups (much faster)")
    p.add_argument("--stale-days", type=int, default=0,
                   help="skip cities refreshed within this many days")
    return p.parse_args()


def targets_for(args):
    """Decide which (city, country) pairs to fetch."""
    if args.city:
        if not args.country:
            sys.exit("--city requires --country")
        return [(args.city, args.country)]

    pairs = database.get_curated_locations()
    if args.country:
        pairs = [p for p in pairs if p[1].lower() == args.country.lower()]
        if not pairs:
            sys.exit(f"no curated locations found for country {args.country!r}")
    return pairs


def is_fresh(city, country, days):
    """True if this city already has external rows newer than `days`."""
    if not days:
        return False
    row = database.query_db(
        "SELECT max(fetched_at) FROM poi WHERE source <> 'local' "
        "AND location ILIKE %s AND country ILIKE %s",
        (city, country), one=True,
    )
    if not row or not row[0]:
        return False
    return (datetime.now() - row[0]).days < days


def main():
    args = parse_args()
    pairs = targets_for(args)

    print(f"Refreshing {len(pairs)} location(s) from OpenStreetMap "
          f"(limit {args.limit}/category)\n")

    totals = {"inserted": 0, "updated": 0, "skipped": 0, "cities": 0}
    started = time.time()

    for city, country in pairs:
        if is_fresh(city, country, args.stale_days):
            print(f"{city}, {country} — still fresh, skipping")
            continue

        print(f"{city}, {country}")
        found = external_pois.fetch_city(
            city, country,
            limit=args.limit,
            with_popularity=not args.no_popularity,
        )
        if not found:
            print("  nothing found\n")
            continue

        inserted, updated, skipped = database.upsert_external_pois(found)
        print(f"  -> {inserted} new, {updated} updated, "
              f"{skipped} skipped (already curated)\n")

        totals["inserted"] += inserted
        totals["updated"] += updated
        totals["skipped"] += skipped
        totals["cities"] += 1

    elapsed = time.time() - started
    print(f"Done in {elapsed:.0f}s across {totals['cities']} cities: "
          f"{totals['inserted']} new, {totals['updated']} updated, "
          f"{totals['skipped']} skipped.")

    counts = database.query_db(
        "SELECT source, count(*) FROM poi GROUP BY source ORDER BY source"
    )
    for source, count in counts:
        print(f"  {source:6} {count}")


if __name__ == "__main__":
    main()
