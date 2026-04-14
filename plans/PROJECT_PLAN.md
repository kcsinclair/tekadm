# tekadm Project Plan

Last updated: 2026-04-14

## Current State

### Completed Scripts

| Script | Description | Status |
|--------|-------------|--------|
| `bin/swap.sh` | Per-process swap usage on Linux via `/proc` | Done |
| `bin/audit-linux.sh` | Linux security hardening audit (~80 controls, 9 categories) | Done |
| `bin/apache-logs.py` | Apache/Nginx access log analyzer with traffic reports | Done |
| `bin/ipsum-update.sh` | Updates IPSUM threat intelligence IP list | Done |
| `bin/log-datename.sh` | Rename log files by appending date from first log line | Done |
| `htdocs/api-tester.php` | Standalone PHP CRUD API endpoint for API testing | Done |

### apache-logs.py Features

- IPv4 and IPv6 log line parsing (bare and bracketed IPv6, escaped quotes)
- User agent classification (browsers, bots, crawlers)
- Suspect IP detection via IPSUM threat intelligence
- GeoIP country lookup for both IPv4 and IPv6 (MaxMind GeoLite2)
- Multiple file processing with date-ordered sorting (oldest first)
- CSV export (IP traffic, endpoint summary, URL type summary)
- Visualizations: user agent bar chart, country bar chart, world heatmap
- Line filtering via regex (`-i` option)

### Infrastructure

- `install.sh` / `init.sh` for PATH setup
- Python venv at `python/` for apache-logs.py dependencies
- Test suite: `test/test_parse_log_lines.py` for log line parsing
- Data dependencies: `ipsum/` (threat IPs), `GeoLite2/` (country DB)
- Implementation plans archived in `plans/` alongside PROJECT_PLAN.md

## Planned Work

From CLAUDE.md project scope and roadmap:

### Near Term
- SAR data visualization (TUI) — system activity report viewer
- Cron-based monitoring (e.g., top every 5 minutes with historical capture)

### Ongoing
- Expand test coverage for apache-logs.py (new log line formats as found)
- Keep IPSUM and GeoLite2 data up to date

### Future Ideas
- Swap/memory analysis improvements
- Additional security hardening checks
- More Python-based tools via pyenv
- OS detection for all scripts (Linux/Mac compatibility)

## Recent Changes

### 2026-04-14
- Fixed log parsing: bare IPv6 addresses, escaped quotes in referer/user-agent
- Added IPv6 GeoIP country lookup via GeoLite2-Country-Blocks-IPv6.csv
- Files now processed in chronological order (sorted by first timestamp)
- Added test suite for log line parsing (`test/test_parse_log_lines.py`)
- Updated READMEs
- Added `plans/` folder with project plan and implementation plan archiving
- Archived implementation plans: `geolite2-country-lookup.md`, `copy-plans-to-project.md`
- Added `htdocs/api-tester.php` — standalone PHP CRUD API for API testing (animals dataset, JSON file storage, token auth)
- Added HTML browser view to api-tester.php — serves styled table when accessed from a browser, JSON for API clients
- Fixed Bearer token auth on Apache CGI/FastCGI — added apache_request_headers() fallback and X-API-Token custom header support

### 2026-04-15
- Added `bin/log-datename.sh` — renames log files by appending date from first Apache timestamp
- Expanded user agent classification with new categories: curl, Python-Client, Go-Client, Node-Client, Bun-Client, Feed-Reader, Security-Scanner, Link-Checker, Apple-Networking, Turnitin, Substack, Amazon-Service, Terra-Cotta, Empty User Agent, LinkedInBot, Checkbot
