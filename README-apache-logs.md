# apache-logs.py

A Python utility for parsing and analyzing Apache/Nginx web server access logs. Generates comprehensive traffic summaries by IP address, user agent type, endpoint, and URL patterns with request counts and timeline information.

## Features

- **Traffic Summary by IP**: Aggregates request counts and user agents by IP address
- **Suspect IP Detection**: Flags IPs found in the IPSUM threat intelligence list (`ipsum/ipsum-bad.txt`)
- **GeoIP Country Lookup**: Maps IPv4 addresses to country and continent using MaxMind GeoLite2 database
- **User Agent Classification**: Automatically categorizes user agents (browsers, bots, crawlers, etc.)
- **Endpoint Analysis**: Tracks individual endpoint access with method, full path, and short endpoint pattern
- **URL Pattern Analysis**: Groups endpoints by their first two path segments for high-level traffic patterns
- **IPv4 and IPv6 Support**: Parses both address formats from access logs
- **Multiple File Support**: Processes single or multiple log files with wildcard patterns
- **Line Filtering**: Ignore log lines matching a regex pattern (e.g., exclude specific bots)
- **CSV Export**: Outputs merged results from multiple files into organized CSV reports
- **Visualization**: Generates bar charts (user agent type, country) and a world heatmap of traffic by country

## Usage

```bash
python apache-logs.py <log_file_pattern> [-o <output_prefix>] [-i <ignore_regex>]
```

### Arguments

- `log_file_pattern`: Path to log file or wildcard pattern (e.g., `/var/log/apache2/access*.log`)
- `-o, --output`: Output CSV prefix (default: `traffic_summary.csv`)
- `-i, --ignore`: Regex pattern to ignore matching log lines (e.g., `"ClaudeBot|SemrushBot"`)

### Examples

**Single file analysis:**
```bash
python apache-logs.py /var/log/apache2/access.log
```

**Multiple files with wildcard:**
```bash
python apache-logs.py "/var/log/apache2/access*.log"
```

**Custom output prefix:**
```bash
python apache-logs.py "/var/log/apache2/access_*.log" -o monthly_report
```

**Ignore specific bots:**
```bash
python apache-logs.py access.log -i "ClaudeBot"
```

**Ignore multiple patterns:**
```bash
python apache-logs.py access.log -i "ClaudeBot|SemrushBot|Baiduspider" -o filtered_report
```

## Output Files

When processing logs, the script generates six output files with the specified prefix:

### 1. `{prefix}.csv` - IP and User Agent Traffic
Detailed breakdown by IP address and user agent.

**Columns:**
- IP Address (IPv4 or IPv6)
- IP Status (`Suspect IP Address` or `IP Address OK` — checked against IPSUM threat list)
- Country (country name from GeoLite2, or `N/A` for IPv6, `Unknown` if not found)
- Country Code (ISO 3166-1 alpha-2 code, e.g., `US`, `AU`, `CN`)
- Continent (continent name, e.g., `North America`, `Asia`, `Europe`)
- Network Subnet (IPv4: /24 subnet, IPv6: /64 subnet)
- Network Supernet (IPv4: /16 block, IPv6: /48 block)
- Agent Requests (requests from this agent)
- First Seen (earliest timestamp)
- Last Seen (latest timestamp)
- User Agent Type (classified category)
- User Agent (full user agent string)
- IP Total Requests (total from this IP)
- Percentage of IP (this agent's share of IP traffic)

### 2. `{prefix}_by_agent_type.png` - User Agent Type Chart
Horizontal bar chart showing total request counts by user agent type classification.

**Categories:**
- Browser (Mozilla, Chrome, Safari, Firefox, Edge, Opera)
- Googlebot, Bingbot, Yandex, DuckDuckBot, Slurp
- ClaudeBot, Baiduspider, SemrushBot
- Crawler (generic crawlers/spiders/bots)
- Unknown (unclassified user agents)

### 3. `{prefix}_by_country.png` - Country Bar Chart
Horizontal bar chart showing total request counts by country (top 25, remainder grouped as "Other").

### 4. `{prefix}_country_map.png` - Country World Heatmap
Choropleth world map with countries colour-coded by request volume. Uses a log-scale blue gradient from light (few requests) to dark navy (most requests). Generated with plotly and exported as PNG (or SVG if the output filename ends in `.svg`).

### 5. `{prefix}_endpoint_summary.csv` - Endpoint Details
Individual endpoint statistics.

**Columns:**
- Method (HTTP method: GET, POST, PUT, DELETE, etc.)
- Endpoint (full request path, truncated to 64 characters)
- Short Endpoint (first two path segments, e.g., `/shop/product`)
- Request Count (number of requests to this endpoint)
- First Seen (earliest request timestamp)
- Last Seen (latest request timestamp)

### 6. `{prefix}_url_type_summary.csv` - URL Pattern Analysis
High-level URL patterns grouped by method and first two path segments.

**Columns:**
- Method (HTTP method)
- URL Type (normalized path pattern, e.g., `/api/v1`)
- Request Count (total requests matching this pattern)
- First Seen (earliest request timestamp)
- Last Seen (latest request timestamp)

## Log Format

The script expects Apache/Nginx combined log format and supports both **IPv4 and IPv6** addresses:

```
<IP> - - [<timestamp>] "<REQUEST>" <STATUS> <BYTES> "<REFERER>" "<USER_AGENT>"
```

**IPv4 Example:**
```
192.168.1.100 - - [13/Mar/2026:14:07:06 +0000] "GET /shop/product/123 HTTP/1.1" 200 1024 "-" "Mozilla/5.0"
```

**IPv6 Example:**
```
[2400:cb00:548:1000:4725:8fb3:735e:7194] - - [13/Mar/2026:14:07:06 +0000] "POST /api/search HTTP/1.1" 200 2048 "-" "curl/7.64.1"
```

**Note:** IPv6 addresses should be enclosed in square brackets `[]`, which is the Apache/Nginx standard format.

## Data Processing

### Endpoint Extraction
- Separates HTTP method from the path
- Removes query strings (everything after `?`)
- Handles URL-encoded quotes (`%22`)
- Truncates to 64 characters for readability

### URL Type Grouping
- Extracts first two path segments from each endpoint
- Groups all endpoints sharing the same pattern together
- Separated by HTTP method (GET, POST, etc. are distinct)

### User Agent Classification
Pattern-based classification with support for:
- Search engine crawlers (Google, Bing, Yahoo, Yandex, DuckDuck)
- Content bots (Semrush, Baidu, Claude)
- General browsers and crawlers
- Fallback to "Unknown" for unrecognized agents

### Suspect IP Detection (IPSUM)
- Loads the IPSUM threat intelligence list from `ipsum/ipsum-bad.txt` (one IP per line)
- Each IP from the log is checked against this set
- Results appear in the `IP Status` column: `Suspect IP Address` or `IP Address OK`
- If the IPSUM file is missing, a warning is printed and all IPs default to `IP Address OK`

### GeoIP Country Lookup (GeoLite2)
- Uses MaxMind GeoLite2 Country database files from the `GeoLite2/` folder:
  - `GeoLite2-Country-Blocks-IPv4.csv` — CIDR network ranges mapped to geoname IDs
  - `GeoLite2-Country-Locations-en.csv` — geoname IDs mapped to country/continent names
- CIDR blocks are loaded into a sorted list and matched via binary search for performance
- Falls back to `registered_country_geoname_id` when primary `geoname_id` is empty
- IPv6 geo lookup is not yet supported (columns show `N/A`)
- If GeoLite2 files are missing, a warning is printed and country columns show `Unknown`

### Network Blocks
**IPv4:**
- `/24` subnet: Identifies the network subnet (typically an ISP provider block)
- `/16` supernet: Identifies the larger network range

**IPv6:**
- `/64` subnet: Identifies the network subnet (standard IPv6 subnet size)
- `/48` supernet: Identifies the larger network allocation (typical ISP allocation)

## Merging Multiple Files

When processing multiple log files with a wildcard pattern, the script:
1. Parses each file independently
2. Merges all traffic summaries while tracking earliest and latest timestamps
3. Combines results into single CSV files
4. Generates aggregated statistics across all files

## Performance Notes

- Processes files line-by-line for memory efficiency
- Works with large log files (millions of requests)
- Warning messages printed for unparseable lines
- Processing time depends on log file size and disk speed

## Requirements

- Python 3.6+
- matplotlib (for bar charts)
- plotly (for world heatmap)
- kaleido (for plotly PNG/SVG export)
- Standard library: re, argparse, bisect, csv, ipaddress, collections, pathlib, glob

Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Data Dependencies

The following data files are expected relative to the project root. The script degrades gracefully if they are missing (prints a warning and uses defaults).

| Folder | File | Purpose |
|--------|------|---------|
| `ipsum/` | `ipsum-bad.txt` | IPSUM threat intelligence IP list (one IP per line) |
| `GeoLite2/` | `GeoLite2-Country-Blocks-IPv4.csv` | MaxMind GeoLite2 IPv4 CIDR-to-geoname mapping |
| `GeoLite2/` | `GeoLite2-Country-Locations-en.csv` | MaxMind GeoLite2 geoname-to-country/continent mapping |

**IPSUM**: Updated via `bin/ipsum-update.sh`. See [stamparm/ipsum](https://github.com/stamparm/ipsum) for details.

**GeoLite2**: Download from [MaxMind](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data). Requires a free MaxMind account [MaxMind Signup](https://www.maxmind.com/en/geolite2/signup).

## Examples

### Analyze a single day's logs:
```bash
python apache-logs.py /var/log/apache2/access.log -o 2026-03-18_analysis
```

Generates:
- `2026-03-18_analysis.csv`
- `2026-03-18_analysis_by_agent_type.png`
- `2026-03-18_analysis_by_country.png`
- `2026-03-18_analysis_country_map.png`
- `2026-03-18_analysis_endpoint_summary.csv`
- `2026-03-18_analysis_url_type_summary.csv`

### Analyze a week's worth of rotated logs:
```bash
python apache-logs.py "/var/log/apache2/access.log.*" -o weekly_report
```

### Identify bot traffic:
Look for high request counts from "Crawler" or specific bot types in `{prefix}_by_agent_type.png` and `{prefix}.csv`.

### Analyze API endpoint patterns:
Check `{prefix}_url_type_summary.csv` for `/api/*` patterns and their request volumes.

### Filter out noisy bots:
```bash
python apache-logs.py access.log -i "ClaudeBot|SemrushBot|Baiduspider" -o human_traffic
```
The `-i` option accepts any Python regex. Matching lines are skipped before parsing, and the count of ignored lines is reported per file.

### Find traffic spikes:
Compare request counts across timestamps in `{prefix}_endpoint_summary.csv` or `{prefix}_url_type_summary.csv`.

---

Built with [Claude](https://claude.ai/code)
