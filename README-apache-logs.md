# apache-logs.py

A Python utility for parsing and analyzing Apache/Nginx web server access logs. Generates comprehensive traffic summaries by IP address, user agent type, endpoint, and URL patterns with request counts and timeline information.

## Features

- **Traffic Summary by IP**: Aggregates request counts and user agents by IP address
- **User Agent Classification**: Automatically categorizes user agents (browsers, bots, crawlers, etc.)
- **Endpoint Analysis**: Tracks individual endpoint access with method, full path, and short endpoint pattern
- **URL Pattern Analysis**: Groups endpoints by their first two path segments for high-level traffic patterns
- **Multiple File Support**: Processes single or multiple log files with wildcard patterns
- **CSV Export**: Outputs merged results from multiple files into organized CSV reports
- **Visualization**: Generates bar charts showing traffic distribution by user agent type

## Usage

```bash
python apache-logs.py <log_file_pattern> [-o <output_prefix>]
```

### Arguments

- `log_file_pattern`: Path to log file or wildcard pattern (e.g., `/var/log/apache2/access*.log`)
- `-o, --output`: Output CSV prefix (default: `traffic_summary.csv`)

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

## Output Files

When processing logs, the script generates four output files with the specified prefix:

### 1. `{prefix}.csv` - IP and User Agent Traffic
Detailed breakdown by IP address and user agent.

**Columns:**
- IP Address
- IP Block /24 (CIDR network block)
- IP Block /16 (larger network block)
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

### 3. `{prefix}_endpoint_summary.csv` - Endpoint Details
Individual endpoint statistics.

**Columns:**
- Method (HTTP method: GET, POST, PUT, DELETE, etc.)
- Endpoint (full request path, truncated to 64 characters)
- Short Endpoint (first two path segments, e.g., `/shop/product`)
- Request Count (number of requests to this endpoint)
- First Seen (earliest request timestamp)
- Last Seen (latest request timestamp)

### 4. `{prefix}_url_type_summary.csv` - URL Pattern Analysis
High-level URL patterns grouped by method and first two path segments.

**Columns:**
- Method (HTTP method)
- URL Type (normalized path pattern, e.g., `/api/v1`)
- Request Count (total requests matching this pattern)
- First Seen (earliest request timestamp)
- Last Seen (latest request timestamp)

## Log Format

The script expects Apache/Nginx combined log format:

```
<IP> - - [<timestamp>] "<REQUEST>" <STATUS> <BYTES> "<REFERER>" "<USER_AGENT>"
```

Example:
```
192.168.1.100 - - [13/Mar/2026:14:07:06 +0000] "GET /shop/product/123 HTTP/1.1" 200 1024 "-" "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
```

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

### IP Network Blocks
- `/24` block: Identifies the /24 subnet (typically an ISP provider block)
- `/16` block: Identifies the /16 supernet (broader network range)

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
- matplotlib (for chart generation)
- Standard library: re, argparse, ipaddress, collections, pathlib, glob

## Examples

### Analyze a single day's logs:
```bash
python apache-logs.py /var/log/apache2/access.log -o 2026-03-18_analysis
```

Generates:
- `2026-03-18_analysis.csv`
- `2026-03-18_analysis_by_agent_type.png`
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

### Find traffic spikes:
Compare request counts across timestamps in `{prefix}_endpoint_summary.csv` or `{prefix}_url_type_summary.csv`.
