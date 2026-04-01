# ripe-subnets-fetcher

IP subnets and ASNs allocated to organizations in a given country by RIPE NCC.

Updated daily via GitHub Actions. Use for policy-based routing on your router (OpenWrt, MikroTik, etc.) — route specific country's IPs directly, everything else through a tunnel.

## Files

Output goes to `countries/{cc}/`:

| File | Description |
|---|---|
| `subnets-v4.txt` | IPv4 CIDR list, one prefix per line, sorted by IP |
| `subnets-v6.txt` | IPv6 CIDR list |
| `subnets.csv` | Full data: ASN, subnet, organization name |

### CSV format

```csv
ASN,subnet,name
12389,5.3.0.0/16,ROSTELECOM-AS PJSC Rostelecom
12389,5.100.64.0/18,ROSTELECOM-AS PJSC Rostelecom
0,2.56.88.0/22,McHost LLC
```

`ASN=0` means the organization has IP blocks but no AS number of its own. Organization names for these entries come from RIPE membership allocation list.

## Router usage (OpenWrt)

Add to crontab (`crontab -e`):

```sh
0 5 * * * curl -sfo /tmp/ru-v4.txt https://raw.githubusercontent.com/<user>/ripe-subnets-fetcher/main/countries/ru/subnets-v4.txt && mv /tmp/ru-v4.txt /etc/ru-subnets.txt
```

## Data sources

- [delegated-ripencc-extended](https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest.txt) — RIPE NCC delegation registry. Contains all ASNs, IPv4 and IPv6 blocks with country and organization binding (`opaque-id`). The `opaque-id` field links ASNs and IP blocks belonging to the same organization.
- [asn.txt](https://ftp.ripe.net/ripe/asnames/asn.txt) — autonomous system names.
- [alloclist.txt](https://ftp.ripe.net/ripe/stats/membership/alloclist.txt) — RIPE membership allocation list. Provides organization names for IP blocks without an associated ASN.

Uses **registration-based** data (blocks allocated to organizations in a given country), not routing-based (BGP announcements). Foreign companies with points of presence in a country (Cloudflare, Google, etc.) are excluded.

## Running

```sh
python fetch_subnets.py RU             # output to countries/ru/
python fetch_subnets.py DE             # output to countries/de/
```

Python 3.13+, no external dependencies. Takes ~6 seconds.

## Auto-update

GitHub Actions ([`.github/workflows/update.yml`](.github/workflows/update.yml)) runs daily at 16:00 UTC. Commits updated files only if data has changed.
