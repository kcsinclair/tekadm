# Plan: Add GeoLite2 Country Lookup to apache-logs.py

## Context
The user has downloaded MaxMind GeoLite2 country database files into `GeoLite2/`. We need to map each IPv4 address from the logs to its country and continent, adding three new columns (`country_name`, `country_iso_code`, `continent_name`) to the main traffic summary CSV.

## Data Files
- `GeoLite2/GeoLite2-Country-Blocks-IPv4.csv` — maps CIDR networks to `geoname_id` (use `geoname_id` column, fall back to `registered_country_geoname_id` if empty)
- `GeoLite2/GeoLite2-Country-Locations-en.csv` — maps `geoname_id` to `country_name`, `country_iso_code`, `continent_name`

## Approach

### 1. Add `load_geolite2_locations()` function (~line 222, near other loaders)
- Reads `GeoLite2/GeoLite2-Country-Locations-en.csv` via `csv.DictReader`
- Returns `dict[str, dict]`: `{geoname_id: {country_name, country_iso_code, continent_name}}`
- Path resolved relative to script: `Path(__file__).resolve().parent.parent / 'GeoLite2' / ...`

### 2. Add `load_geolite2_blocks()` function
- Reads `GeoLite2/GeoLite2-Country-Blocks-IPv4.csv` via `csv.DictReader`
- For each row, converts CIDR `network` to `(start_int, end_int, geoname_id)` using `ipaddress.ip_network()`
- Stores in a sorted list by `start_int`
- Returns the sorted list

### 3. Add `lookup_country(ip, blocks, locations)` function
- Converts IP string to int via `ipaddress.ip_address()`
- Binary searches (`bisect`) the sorted blocks list to find the matching CIDR range
- Returns `(country_name, country_iso_code, continent_name)` or `("Unknown", "Unknown", "Unknown")` if not found

### 4. Update `export_to_csv()` (~line 296)
- Load geo data once at the top: `locations = load_geolite2_locations()`, `blocks = load_geolite2_blocks()`
- Add three columns to CSV header after `Network Supernet`: `Country`, `Country Code`, `Continent`
- For each IP, call `lookup_country()` and include the results in the row
- IPv6 addresses get `"N/A"` for all three geo columns (IPv4 only for now)

### 5. Add `import bisect` at top of file (line ~4)

## Files to modify
- `bin/apache-logs.py` — add 3 functions, 1 import, update `export_to_csv()`

## Verification
- Run `python bin/apache-logs.py <logfile> -o test_output.csv`
- Open CSV and confirm Country, Country Code, Continent columns populated
- Spot-check a known IP (e.g., `1.0.1.0` should resolve to geoname_id `1814991` = China)
