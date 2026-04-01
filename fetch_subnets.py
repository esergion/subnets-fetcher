#!/usr/bin/env python3
"""
Fetches IP subnets allocated to organizations in a given country via RIPE NCC.
Output: CSV (ASN, subnet, name) and plain CIDR lists (IPv4/IPv6).

Data sources:
  - RIPE NCC delegated-extended: allocations with opaque-id to link ASN↔prefix
  - RIPE FTP asn.txt: human-readable AS names
  - RIPE FTP alloclist.txt: org names for members (fills gaps where ASN=0)
"""

import argparse
import csv
import ipaddress
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

DELEGATED_URL = "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest.txt"
ASN_NAMES_URL = "https://ftp.ripe.net/ripe/asnames/asn.txt"
ALLOCLIST_URL = "https://ftp.ripe.net/ripe/stats/membership/alloclist.txt"

MAX_RETRIES = 3
RETRY_DELAY = 2.0


def fetch_url(url: str, timeout: int = 120) -> bytes:
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "ripe-subnets-fetcher/4.0"
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                print(f"[error] {exc} — retry in {delay:.1f}s", file=sys.stderr)
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("unreachable")


def load_asn_names() -> dict[int, str]:
    print("[*] Fetching ASN names...", file=sys.stderr)
    text = fetch_url(ASN_NAMES_URL).decode("utf-8", errors="replace")
    names = {}
    for line in text.splitlines():
        asn, _, rest = line.partition(" ")
        if asn.isdigit() and rest:
            name, _, _ = rest.rpartition(", ")
            names[int(asn)] = name or rest
    print(f"[*]   {len(names)} names loaded", file=sys.stderr)
    return names


def load_alloclist(cc: str) -> dict[str, str]:
    """Parse alloclist.txt, return {prefix: org_name} for members of given country."""
    print("[*] Fetching alloclist (org names)...", file=sys.stderr)
    text = fetch_url(ALLOCLIST_URL).decode("utf-8", errors="replace")
    prefix = cc.lower() + "."
    orgs: dict[str, str] = {}
    current_name: str | None = None
    expect_name = False
    for line in text.splitlines():
        if line.startswith(prefix):
            expect_name = True
            current_name = None
        elif not line.startswith(" ") and line.strip():
            expect_name = False
            current_name = None
        elif expect_name and line.startswith("    ") and line.strip():
            current_name = line.strip()
            expect_name = False
        elif current_name and line.startswith("    ") and line.strip():
            parts = line.split()
            if len(parts) >= 2 and "/" in parts[1]:
                orgs[parts[1]] = current_name
    print(f"[*]   {len(orgs)} {cc} prefixes with org names", file=sys.stderr)
    return orgs


def load_delegated(cc: str) -> dict[str, dict]:
    """Parse delegated-extended, group entries for given country by opaque-id."""
    print("[*] Fetching delegated-ripencc-extended...", file=sys.stderr)
    text = fetch_url(DELEGATED_URL).decode("utf-8", errors="replace")

    orgs: dict[str, dict] = defaultdict(lambda: {"asns": [], "v4": [], "v6": []})
    for line in text.splitlines():
        if line.startswith("#") or line.startswith("2|") or "|*|" in line:
            continue
        parts = line.split("|")
        if len(parts) < 8 or parts[1] != cc:
            continue

        oid, typ = parts[7], parts[2]
        if typ == "asn":
            orgs[oid]["asns"].append(int(parts[3]))
        elif typ == "ipv4":
            start = ipaddress.ip_address(parts[3])
            end = start + int(parts[4]) - 1
            orgs[oid]["v4"].extend(ipaddress.summarize_address_range(start, end))
        elif typ == "ipv6":
            orgs[oid]["v6"].append(ipaddress.ip_network(f"{parts[3]}/{parts[4]}", strict=False))

    print(f"[*]   {len(orgs)} organizations parsed", file=sys.stderr)
    return dict(orgs)


def main(cc: str) -> None:
    asn_names = load_asn_names()
    alloc_names = load_alloclist(cc)
    orgs = load_delegated(cc)

    # Build rows: for each org, pair its ASN(s) with its prefixes
    rows: list[tuple[int, str, str]] = []
    all_v4: set[ipaddress.IPv4Network] = set()
    all_v6: set[ipaddress.IPv6Network] = set()

    for org in orgs.values():
        asn = org["asns"][0] if org["asns"] else 0
        name = asn_names.get(asn, "") if asn else ""
        for net in org["v4"]:
            subnet = str(net)
            row_name = name or alloc_names.get(subnet, "")
            rows.append((asn, subnet, row_name))
            all_v4.add(net)
        for net in org["v6"]:
            subnet = str(net)
            row_name = name or alloc_names.get(subnet, "")
            rows.append((asn, subnet, row_name))
            all_v6.add(net)

    rows.sort(key=lambda r: (r[0], ipaddress.ip_network(r[1]).version, ipaddress.ip_network(r[1])))
    v4_sorted = sorted(all_v4)
    v6_sorted = sorted(all_v6)

    # Stats
    with_asn = sum(1 for r in rows if r[0])
    with_name = sum(1 for r in rows if r[2])
    print(f"[*] {len(rows)} subnets ({with_asn} with ASN, {len(rows) - with_asn} without)", file=sys.stderr)
    print(f"[*] {with_name} with name ({with_name * 100 / len(rows):.1f}%)", file=sys.stderr)

    script_dir = Path(__file__).resolve().parent
    country_dir = script_dir / "countries" / cc.lower()
    country_dir.mkdir(parents=True, exist_ok=True)

    with open(country_dir / "subnets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ASN", "subnet", "name"])
        w.writerows(rows)

    (country_dir / "subnets-v4.txt").write_text("\n".join(str(n) for n in v4_sorted) + "\n")
    (country_dir / "subnets-v6.txt").write_text("\n".join(str(n) for n in v6_sorted) + "\n")

    print(f"[*] Done: {len(v4_sorted)} IPv4 + {len(v6_sorted)} IPv6 prefixes", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch IP subnets allocated to organizations in a given country via RIPE NCC."
    )
    parser.add_argument(
        "country",
        help="ISO 3166-1 alpha-2 country code (e.g. RU, DE, US)",
    )
    args = parser.parse_args()
    cc = args.country.upper()

    start = time.monotonic()
    main(cc)
    print(f"[*] Total time: {time.monotonic() - start:.1f}s", file=sys.stderr)
