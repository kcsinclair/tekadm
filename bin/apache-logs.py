# 
# Copyright (c) 2026 Keith Sinclair
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# 

import re
import argparse
import bisect
import csv
import ipaddress
from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import glob

def format_timestamp(timestamp_str):
    """Convert Apache log timestamp to Excel-friendly format (DD/MMM/YYYY HH:MM:SS)."""
    # Apache format: "13/Mar/2026:14:07:06 +0000"
    # Remove timezone and replace colon before time with space
    timestamp_clean = timestamp_str.split(' ')[0]  # Gets "13/Mar/2026:14:07:06"
    return timestamp_clean.replace(':', ' ', 1)  # Replace first colon with space


def extract_method(request_line):
    """
    Extract HTTP method from request line.
    Request line format: "GET /path HTTP/1.0"
    """
    parts = request_line.split()
    return parts[0] if parts else "UNKNOWN"


def extract_endpoint(request_line):
    """
    Extract and normalize endpoint from request line (without method).
    Handles special cases like URL-encoded strings split on %22 and query strings on ?.
    Returns truncated endpoint (first 64 characters).
    """
    # Request line format: "GET /path HTTP/1.0"
    # Remove the HTTP version part
    parts = request_line.rsplit(' ', 1)
    if len(parts) == 2:
        method_and_path = parts[0]
    else:
        method_and_path = request_line

    # Extract just the path (remove method)
    path_parts = method_and_path.split(' ', 1)
    path = path_parts[1] if len(path_parts) > 1 else path_parts[0]

    # Handle URLs with %22 (encoded quote) - split and take first part
    if '%22' in path:
        path = path.split('%22')[0]

    # Handle query strings - split on ? and take the base path
    if '?' in path:
        path = path.split('?')[0]

    # Truncate to 64 characters
    truncated = path[:64]
    return truncated


def extract_url_type(endpoint):
    """
    Extract URL type from endpoint (first two path segments).
    Example: "/shop/product/44204" -> "/shop/product"
    """
    # endpoint is already just the path (no method)
    path = endpoint

    # Split path on / and get first two segments
    path_segments = [seg for seg in path.split('/') if seg]  # Filter out empty strings

    if len(path_segments) <= 1:
        # If only root or one segment, return as-is
        return path
    else:
        # Return first two path segments
        url_type = f"/{path_segments[0]}/{path_segments[1]}"
        return url_type


def parse_access_log(log_file, ignore_pattern=None):
    """
    Parse web server access logs and summarize traffic by IP, user agent, and endpoint.
    Works with Apache/Nginx combined log format.
    Lines matching ignore_pattern (regex) are skipped.
    """

    # Apache/Nginx combined log format pattern
    # Matches both IPv4 (192.168.1.1) and IPv6 ([2400:cb00:548:1000:4725:8fb3:735e:7194])
    log_pattern = re.compile(
        r'(\d+\.\d+\.\d+\.\d+|\[[0-9a-fA-F:]+\])\s+'  # IP address (IPv4 or IPv6)
        r'.*?\[([^\]]+)\]\s+'  # Timestamp
        r'"([A-Z]+\s+\S+\s+\S+)"\s+'  # Request
        r'(\d+)\s+'  # Status code
        r'(\d+|-)\s+'  # Bytes sent
        r'"([^"]*)"\s+'  # Referer
        r'"([^"]*)"'  # User agent
    )

    # Data structure: {ip: {'count': int, 'user_agents': {agent: {'count': int, 'first_seen': timestamp, 'last_seen': timestamp}}}}
    traffic_summary = defaultdict(lambda: {
        'count': 0,
        'user_agents': defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None})
    })

    # Data structure for endpoints: {endpoint: {'count': int, 'first_seen': timestamp, 'last_seen': timestamp, 'method': str, 'url_type': str}}
    endpoint_summary = defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None, 'method': None, 'url_type': None})

    # Data structure for URL types: {url_type: {'count': int, 'first_seen': timestamp, 'last_seen': timestamp, 'method': str}}
    url_type_summary = defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None, 'method': None})

    ignore_re = re.compile(ignore_pattern) if ignore_pattern else None
    ignored_count = 0

    try:
        with open(log_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if ignore_re and ignore_re.search(line):
                    ignored_count += 1
                    continue
                match = log_pattern.search(line)
                if match:
                    ip = match.group(1)
                    timestamp = format_timestamp(match.group(2))
                    request_line = match.group(3)
                    user_agent = match.group(7)

                    # Process IP/agent traffic
                    traffic_summary[ip]['count'] += 1
                    agent_data = traffic_summary[ip]['user_agents'][user_agent]
                    agent_data['count'] += 1

                    if agent_data['first_seen'] is None:
                        agent_data['first_seen'] = timestamp
                    agent_data['last_seen'] = timestamp

                    # Process endpoint traffic
                    method = extract_method(request_line)
                    endpoint = extract_endpoint(request_line)
                    endpoint_data = endpoint_summary[endpoint]
                    endpoint_data['count'] += 1
                    endpoint_data['method'] = method
                    url_type = extract_url_type(endpoint)
                    endpoint_data['url_type'] = url_type

                    if endpoint_data['first_seen'] is None:
                        endpoint_data['first_seen'] = timestamp
                    endpoint_data['last_seen'] = timestamp

                    # Process URL type traffic
                    url_type_key = f"{method} {url_type}"
                    url_type_data = url_type_summary[url_type_key]
                    url_type_data['count'] += 1
                    url_type_data['method'] = method

                    if url_type_data['first_seen'] is None:
                        url_type_data['first_seen'] = timestamp
                    url_type_data['last_seen'] = timestamp
                else:
                    print(f"Warning: Could not parse line {line_num}: {line[:80]}")

    except FileNotFoundError:
        print(f"Error: Log file '{log_file}' not found")
        return None, None, None

    if ignored_count > 0:
        print(f"    Ignored {ignored_count} lines matching pattern: {ignore_pattern}")

    return traffic_summary, endpoint_summary, url_type_summary


def print_summary(traffic_summary):
    """Print a formatted summary of traffic by IP and user agent."""
    
    if not traffic_summary:
        print("No data to display")
        return
    
    print("\n" + "=" * 100)
    print("TRAFFIC SUMMARY BY IP ADDRESS")
    print("=" * 100 + "\n")
    
    # Sort by traffic count (descending)
    sorted_ips = sorted(
        traffic_summary.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )
    
    for ip, data in sorted_ips:
        print(f"IP: {ip}")
        print(f"  Total Requests: {data['count']}")
        print(f"  User Agents:")

        # Sort user agents by count
        sorted_agents = sorted(
            data['user_agents'].items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )

        for agent, agent_data in sorted_agents:
            count = agent_data['count']
            percentage = (count / data['count']) * 100
            print(f"    - {agent[:60]}...")
            print(f"      Requests: {count} ({percentage:.1f}%)")
            print(f"      First Seen: {agent_data['first_seen']}")
            print(f"      Last Seen: {agent_data['last_seen']}")

        print()


def load_suspect_ips():
    """
    Load suspect IP addresses from ipsum/ipsum-bad.txt.
    Returns a set of IP strings for fast lookup.
    """
    ipsum_path = Path(__file__).resolve().parent.parent / 'ipsum' / 'ipsum-bad.txt'
    try:
        with open(ipsum_path, 'r') as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        print(f"Warning: Suspect IP list not found at {ipsum_path} — skipping IP status checks")
        return set()


def load_geolite2_locations():
    """
    Load GeoLite2 country locations lookup.
    Returns dict: {geoname_id: {country_name, country_iso_code, continent_name}}
    """
    locations_path = Path(__file__).resolve().parent.parent / 'GeoLite2' / 'GeoLite2-Country-Locations-en.csv'
    locations = {}
    try:
        with open(locations_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                locations[row['geoname_id']] = {
                    'country_name': row['country_name'],
                    'country_iso_code': row['country_iso_code'],
                    'continent_name': row['continent_name'],
                }
    except FileNotFoundError:
        print(f"Warning: GeoLite2 locations file not found at {locations_path}")
    return locations


def load_geolite2_blocks():
    """
    Load GeoLite2 IPv4 CIDR blocks as a sorted list for binary search.
    Returns list of (start_int, end_int, geoname_id) sorted by start_int.
    """
    blocks_path = Path(__file__).resolve().parent.parent / 'GeoLite2' / 'GeoLite2-Country-Blocks-IPv4.csv'
    blocks = []
    try:
        with open(blocks_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                geoname_id = row['geoname_id'] or row['registered_country_geoname_id']
                if not geoname_id:
                    continue
                network = ipaddress.ip_network(row['network'], strict=False)
                start_int = int(network.network_address)
                end_int = int(network.broadcast_address)
                blocks.append((start_int, end_int, geoname_id))
        blocks.sort(key=lambda x: x[0])
        print(f"  Loaded {len(blocks)} GeoLite2 IPv4 blocks")
    except FileNotFoundError:
        print(f"Warning: GeoLite2 blocks file not found at {blocks_path}")
    return blocks


def lookup_country(ip, blocks, locations):
    """
    Look up country for an IPv4 address using binary search on GeoLite2 blocks.
    Returns (country_name, country_iso_code, continent_name) or ("Unknown", ...) if not found.
    """
    try:
        ip_clean = ip.strip('[]')
        ip_obj = ipaddress.ip_address(ip_clean)

        # IPv6 not supported for geo lookup yet
        if isinstance(ip_obj, ipaddress.IPv6Address):
            return ("N/A", "N/A", "N/A")

        ip_int = int(ip_obj)

        # Binary search: find rightmost block where start_int <= ip_int
        idx = bisect.bisect_right(blocks, (ip_int,)) - 1
        if idx >= 0:
            start_int, end_int, geoname_id = blocks[idx]
            if start_int <= ip_int <= end_int:
                loc = locations.get(geoname_id, {})
                return (
                    loc.get('country_name', 'Unknown'),
                    loc.get('country_iso_code', 'Unknown'),
                    loc.get('continent_name', 'Unknown'),
                )
    except ValueError:
        pass

    return ("Unknown", "Unknown", "Unknown")


def get_ip_blocks(ip):
    """
    Get network blocks for an IP address.
    IPv4: /24 and /16 blocks
    IPv6: /64 and /48 blocks
    """
    try:
        # Remove brackets if present (IPv6 from log format)
        ip_clean = ip.strip('[]')

        # Parse the IP address to determine type
        ip_obj = ipaddress.ip_address(ip_clean)

        if isinstance(ip_obj, ipaddress.IPv4Address):
            # IPv4: use /24 and /16
            block_subnet = str(ipaddress.ip_network(f"{ip_clean}/24", strict=False))
            block_supernet = str(ipaddress.ip_network(f"{ip_clean}/16", strict=False))
        else:
            # IPv6: use /64 and /48
            block_subnet = str(ipaddress.ip_network(f"{ip_clean}/64", strict=False))
            block_supernet = str(ipaddress.ip_network(f"{ip_clean}/48", strict=False))

        return block_subnet, block_supernet
    except ValueError:
        return "N/A", "N/A"


def classify_user_agent(user_agent):
    """
    Classify user agent type based on patterns.
    Add more patterns to the agent_patterns dict as needed.
    """
    # Pattern matching rules: (type, list_of_patterns)
    agent_patterns = {
        'ClaudeBot': ['claudebot', 'claude-web'],
        'Baiduspider': ['baiduspider', 'baidu'],
        'SemrushBot': ['semrushbot', 'semrush'],
        'Googlebot': ['googlebot', 'google'],
        'Bingbot': ['bingbot', 'bing'],
        'Slurp': ['slurp', 'yahoo'],
        'DuckDuckBot': ['duckduckbot', 'duckduck'],
        'Yandex': ['yandex', 'yandeximages'],
        'Crawler': ['crawler', 'spider', 'bot'],
    }

    user_agent_lower = user_agent.lower()

    # Check against patterns in order
    for agent_type, patterns in agent_patterns.items():
        for pattern in patterns:
            if pattern in user_agent_lower:
                return agent_type

    # Default classification based on common browser indicators
    if any(keyword in user_agent_lower for keyword in ['mozilla', 'chrome', 'safari', 'firefox', 'edge', 'opera']):
        return 'Browser'

    return 'Unknown'


def export_to_csv(traffic_summary, output_file='traffic_summary.csv'):
    """Export summary to CSV for further analysis."""

    suspect_ips = load_suspect_ips()
    geo_locations = load_geolite2_locations()
    geo_blocks = load_geolite2_blocks()

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['IP Address', 'IP Status', 'Country', 'Country Code', 'Continent', 'Network Subnet', 'Network Supernet', 'Agent Requests', 'First Seen', 'Last Seen', 'User Agent Type', 'User Agent', 'IP Total Requests', 'Percentage of IP'])

        for ip, data in sorted(traffic_summary.items(), key=lambda x: x[1]['count'], reverse=True):
            block_24, block_16 = get_ip_blocks(ip)
            # Strip brackets for IPv6 before checking suspect list
            ip_clean = ip.strip('[]')
            ip_status = "Suspect IP Address" if ip_clean in suspect_ips else "IP Address OK"
            country_name, country_iso, continent_name = lookup_country(ip, geo_blocks, geo_locations)
            agents_list = sorted(data['user_agents'].items(), key=lambda x: x[1]['count'], reverse=True)

            for idx, (agent, agent_data) in enumerate(agents_list):
                count = agent_data['count']
                percentage = (count / data['count']) * 100
                agent_type = classify_user_agent(agent)
                # Only include IP totals on first agent row for each IP to avoid double-counting
                if idx == 0:
                    writer.writerow([ip, ip_status, country_name, country_iso, continent_name, block_24, block_16, count, agent_data['first_seen'], agent_data['last_seen'], agent_type, agent, data['count'], f"{percentage:.1f}%"])
                else:
                    writer.writerow([ip, ip_status, country_name, country_iso, continent_name, block_24, block_16, count, agent_data['first_seen'], agent_data['last_seen'], agent_type, agent, "", f"{percentage:.1f}%"])

    print(f"Summary exported to {output_file}")


def export_endpoints_to_csv(endpoint_summary, output_file='endpoint_summary.csv'):
    """Export endpoint summary to CSV for further analysis."""

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Method', 'Endpoint', 'Short Endpoint', 'Request Count', 'First Seen', 'Last Seen'])

        # Sort by request count descending
        for endpoint, data in sorted(endpoint_summary.items(), key=lambda x: x[1]['count'], reverse=True):
            writer.writerow([data['method'], endpoint, data['url_type'], data['count'], data['first_seen'], data['last_seen']])

    print(f"Endpoint summary exported to {output_file}")


def export_url_types_to_csv(url_type_summary, output_file='url_type_summary.csv'):
    """Export URL type summary to CSV for further analysis."""

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Method', 'URL Type', 'Request Count', 'First Seen', 'Last Seen'])

        # Sort by request count descending
        for url_type_key, data in sorted(url_type_summary.items(), key=lambda x: x[1]['count'], reverse=True):
            # Extract method and url_type from the key (format: "METHOD /path/to/resource")
            parts = url_type_key.split(' ', 1)
            method = parts[0] if parts else "UNKNOWN"
            url_type = parts[1] if len(parts) > 1 else url_type_key
            writer.writerow([method, url_type, data['count'], data['first_seen'], data['last_seen']])

    print(f"URL type summary exported to {output_file}")


def generate_agent_type_graph(traffic_summary, output_file='agent_type_summary.png'):
    """Generate a bar chart showing total requests by User Agent Type."""

    # Aggregate request counts by agent type
    agent_type_counts = defaultdict(int)

    for ip, data in traffic_summary.items():
        for agent, agent_data in data['user_agents'].items():
            agent_type = classify_user_agent(agent)
            agent_type_counts[agent_type] += agent_data['count']

    # Sort by count descending
    sorted_types = sorted(agent_type_counts.items(), key=lambda x: x[1], reverse=True)
    types, counts = zip(*sorted_types)

    # Create horizontal bar chart
    fig, ax = plt.subplots(figsize=(10, 6))

    bars = ax.barh(types, counts, color='#4C72B0', edgecolor='#333333', linewidth=1.2)

    # Add value labels on bars
    for bar, count in zip(bars, counts):
        width = bar.get_width()
        ax.text(width + max(counts) * 0.01, bar.get_y() + bar.get_height()/2,
                f'{int(count):,}', ha='left', va='center', fontsize=10, fontweight='bold')

    ax.set_xlabel('Number of Requests', fontsize=11, fontweight='bold')
    ax.set_ylabel('User Agent Type', fontsize=11, fontweight='bold')
    ax.set_title('Traffic Summary by User Agent Type', fontsize=13, fontweight='bold', pad=20)

    # Format x-axis with thousand separators
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{int(x):,}'))

    # Remove top and right spines for cleaner look
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Agent type summary chart saved to {output_file}")


def generate_country_graph(traffic_summary, output_file='country_summary.png'):
    """Generate a bar chart showing total requests by country."""

    geo_locations = load_geolite2_locations()
    geo_blocks = load_geolite2_blocks()

    # Aggregate request counts by country
    country_counts = defaultdict(int)

    for ip, data in traffic_summary.items():
        country_name, country_iso, continent_name = lookup_country(ip, geo_blocks, geo_locations)
        country_counts[country_name] += data['count']

    if not country_counts:
        print("No country data available for chart")
        return

    # Sort by count descending
    sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)

    # Limit to top 25 countries for readability
    if len(sorted_countries) > 25:
        top_countries = sorted_countries[:25]
        other_count = sum(count for _, count in sorted_countries[25:])
        top_countries.append(('Other', other_count))
        sorted_countries = top_countries

    countries, counts = zip(*sorted_countries)

    # Create horizontal bar chart
    fig, ax = plt.subplots(figsize=(12, max(6, len(countries) * 0.35)))

    bars = ax.barh(countries, counts, color='#2E86AB', edgecolor='#333333', linewidth=1.2)

    # Add value labels on bars
    for bar, count in zip(bars, counts):
        width = bar.get_width()
        ax.text(width + max(counts) * 0.01, bar.get_y() + bar.get_height()/2,
                f'{int(count):,}', ha='left', va='center', fontsize=9, fontweight='bold')

    ax.set_xlabel('Number of Requests', fontsize=11, fontweight='bold')
    ax.set_ylabel('Country', fontsize=11, fontweight='bold')
    ax.set_title('Traffic Summary by Country', fontsize=13, fontweight='bold', pad=20)

    # Format x-axis with thousand separators
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'{int(x):,}'))

    # Remove top and right spines for cleaner look
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Invert y-axis so highest count is at the top
    ax.invert_yaxis()

    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Country summary chart saved to {output_file}")


def generate_country_map(traffic_summary, output_file='country_map.png'):
    """Generate a world heatmap showing request counts by country using plotly choropleth."""
    import plotly.graph_objects as go
    import math

    # ISO 3166-1 alpha-2 to alpha-3 mapping for plotly (which requires ISO-3)
    ISO2_TO_ISO3 = {
        'AD': 'AND', 'AE': 'ARE', 'AF': 'AFG', 'AG': 'ATG', 'AI': 'AIA', 'AL': 'ALB', 'AM': 'ARM',
        'AO': 'AGO', 'AQ': 'ATA', 'AR': 'ARG', 'AS': 'ASM', 'AT': 'AUT', 'AU': 'AUS', 'AW': 'ABW',
        'AX': 'ALA', 'AZ': 'AZE', 'BA': 'BIH', 'BB': 'BRB', 'BD': 'BGD', 'BE': 'BEL', 'BF': 'BFA',
        'BG': 'BGR', 'BH': 'BHR', 'BI': 'BDI', 'BJ': 'BEN', 'BL': 'BLM', 'BM': 'BMU', 'BN': 'BRN',
        'BO': 'BOL', 'BQ': 'BES', 'BR': 'BRA', 'BS': 'BHS', 'BT': 'BTN', 'BV': 'BVT', 'BW': 'BWA',
        'BY': 'BLR', 'BZ': 'BLZ', 'CA': 'CAN', 'CC': 'CCK', 'CD': 'COD', 'CF': 'CAF', 'CG': 'COG',
        'CH': 'CHE', 'CI': 'CIV', 'CK': 'COK', 'CL': 'CHL', 'CM': 'CMR', 'CN': 'CHN', 'CO': 'COL',
        'CR': 'CRI', 'CU': 'CUB', 'CV': 'CPV', 'CW': 'CUW', 'CX': 'CXR', 'CY': 'CYP', 'CZ': 'CZE',
        'DE': 'DEU', 'DJ': 'DJI', 'DK': 'DNK', 'DM': 'DMA', 'DO': 'DOM', 'DZ': 'DZA', 'EC': 'ECU',
        'EE': 'EST', 'EG': 'EGY', 'EH': 'ESH', 'ER': 'ERI', 'ES': 'ESP', 'ET': 'ETH', 'FI': 'FIN',
        'FJ': 'FJI', 'FK': 'FLK', 'FM': 'FSM', 'FO': 'FRO', 'FR': 'FRA', 'GA': 'GAB', 'GB': 'GBR',
        'GD': 'GRD', 'GE': 'GEO', 'GF': 'GUF', 'GG': 'GGY', 'GH': 'GHA', 'GI': 'GIB', 'GL': 'GRL',
        'GM': 'GMB', 'GN': 'GIN', 'GP': 'GLP', 'GQ': 'GNQ', 'GR': 'GRC', 'GS': 'SGS', 'GT': 'GTM',
        'GU': 'GUM', 'GW': 'GNB', 'GY': 'GUY', 'HK': 'HKG', 'HM': 'HMD', 'HN': 'HND', 'HR': 'HRV',
        'HT': 'HTI', 'HU': 'HUN', 'ID': 'IDN', 'IE': 'IRL', 'IL': 'ISR', 'IM': 'IMN', 'IN': 'IND',
        'IO': 'IOT', 'IQ': 'IRQ', 'IR': 'IRN', 'IS': 'ISL', 'IT': 'ITA', 'JE': 'JEY', 'JM': 'JAM',
        'JO': 'JOR', 'JP': 'JPN', 'KE': 'KEN', 'KG': 'KGZ', 'KH': 'KHM', 'KI': 'KIR', 'KM': 'COM',
        'KN': 'KNA', 'KP': 'PRK', 'KR': 'KOR', 'KW': 'KWT', 'KY': 'CYM', 'KZ': 'KAZ', 'LA': 'LAO',
        'LB': 'LBN', 'LC': 'LCA', 'LI': 'LIE', 'LK': 'LKA', 'LR': 'LBR', 'LS': 'LSO', 'LT': 'LTU',
        'LU': 'LUX', 'LV': 'LVA', 'LY': 'LBY', 'MA': 'MAR', 'MC': 'MCO', 'MD': 'MDA', 'ME': 'MNE',
        'MF': 'MAF', 'MG': 'MDG', 'MH': 'MHL', 'MK': 'MKD', 'ML': 'MLI', 'MM': 'MMR', 'MN': 'MNG',
        'MO': 'MAC', 'MP': 'MNP', 'MQ': 'MTQ', 'MR': 'MRT', 'MS': 'MSR', 'MT': 'MLT', 'MU': 'MUS',
        'MV': 'MDV', 'MW': 'MWI', 'MX': 'MEX', 'MY': 'MYS', 'MZ': 'MOZ', 'NA': 'NAM', 'NC': 'NCL',
        'NE': 'NER', 'NF': 'NFK', 'NG': 'NGA', 'NI': 'NIC', 'NL': 'NLD', 'NO': 'NOR', 'NP': 'NPL',
        'NR': 'NRU', 'NU': 'NIU', 'NZ': 'NZL', 'OM': 'OMN', 'PA': 'PAN', 'PE': 'PER', 'PF': 'PYF',
        'PG': 'PNG', 'PH': 'PHL', 'PK': 'PAK', 'PL': 'POL', 'PM': 'SPM', 'PN': 'PCN', 'PR': 'PRI',
        'PS': 'PSE', 'PT': 'PRT', 'PW': 'PLW', 'PY': 'PRY', 'QA': 'QAT', 'RE': 'REU', 'RO': 'ROU',
        'RS': 'SRB', 'RU': 'RUS', 'RW': 'RWA', 'SA': 'SAU', 'SB': 'SLB', 'SC': 'SYC', 'SD': 'SDN',
        'SE': 'SWE', 'SG': 'SGP', 'SH': 'SHN', 'SI': 'SVN', 'SJ': 'SJM', 'SK': 'SVK', 'SL': 'SLE',
        'SM': 'SMR', 'SN': 'SEN', 'SO': 'SOM', 'SR': 'SUR', 'SS': 'SSD', 'ST': 'STP', 'SV': 'SLV',
        'SX': 'SXM', 'SY': 'SYR', 'SZ': 'SWZ', 'TC': 'TCA', 'TD': 'TCD', 'TF': 'ATF', 'TG': 'TGO',
        'TH': 'THA', 'TJ': 'TJK', 'TK': 'TKL', 'TL': 'TLS', 'TM': 'TKM', 'TN': 'TUN', 'TO': 'TON',
        'TR': 'TUR', 'TT': 'TTO', 'TV': 'TUV', 'TW': 'TWN', 'TZ': 'TZA', 'UA': 'UKR', 'UG': 'UGA',
        'UM': 'UMI', 'US': 'USA', 'UY': 'URY', 'UZ': 'UZB', 'VA': 'VAT', 'VC': 'VCT', 'VE': 'VEN',
        'VG': 'VGB', 'VI': 'VIR', 'VN': 'VNM', 'VU': 'VUT', 'WF': 'WLF', 'WS': 'WSM', 'XK': 'XKX',
        'YE': 'YEM', 'YT': 'MYT', 'ZA': 'ZAF', 'ZM': 'ZMB', 'ZW': 'ZWE',
    }

    geo_locations = load_geolite2_locations()
    geo_blocks = load_geolite2_blocks()

    # Aggregate request counts by ISO country code
    country_code_counts = defaultdict(lambda: {'count': 0, 'name': ''})

    for ip, data in traffic_summary.items():
        country_name, country_iso, continent_name = lookup_country(ip, geo_blocks, geo_locations)
        if country_iso and country_iso not in ('Unknown', 'N/A'):
            country_code_counts[country_iso]['count'] += data['count']
            country_code_counts[country_iso]['name'] = country_name

    if not country_code_counts:
        print("No country data available for map")
        return

    iso3_codes = []
    counts = []
    names = []
    for code, info in country_code_counts.items():
        iso3 = ISO2_TO_ISO3.get(code)
        if not iso3:
            continue
        iso3_codes.append(iso3)
        counts.append(info['count'])
        names.append(info['name'])

    # Use log scale for better colour distribution across wide ranges
    log_counts = [math.log10(c) if c > 0 else 0 for c in counts]

    # Build hover text with actual counts
    hover_text = [f"{name}<br>{count:,} requests" for name, count in zip(names, counts)]

    fig = go.Figure(data=go.Choropleth(
        locations=iso3_codes,
        z=log_counts,
        text=hover_text,
        hoverinfo='text',
        locationmode='ISO-3',
        colorscale=[
            [0.0, '#f7fbff'],
            [0.2, '#c6dbef'],
            [0.4, '#6baed6'],
            [0.6, '#2171b5'],
            [0.8, '#08519c'],
            [1.0, '#08306b'],
        ],
        marker_line_color='#333333',
        marker_line_width=0.5,
        colorbar=dict(
            title=dict(text='Requests'),
            tickvals=[1, 2, 3, 4, 5, 6],
            ticktext=['10', '100', '1K', '10K', '100K', '1M'],
        ),
    ))

    fig.update_layout(
        title=dict(
            text='Traffic by Country',
            font=dict(size=16, family='Arial, sans-serif'),
            x=0.5,
        ),
        geo=dict(
            showframe=False,
            showcoastlines=True,
            coastlinecolor='#999999',
            projection_type='natural earth',
            landcolor='#f0f0f0',
            showocean=True,
            oceancolor='#e6f2ff',
        ),
        width=1200,
        height=600,
        margin=dict(l=10, r=10, t=50, b=10),
    )

    # Determine format from file extension
    if output_file.endswith('.svg'):
        fig.write_image(output_file, format='svg')
    else:
        fig.write_image(output_file, format='png', scale=2)

    print(f"Country heatmap saved to {output_file}")


def merge_traffic_summaries(summaries):
    """Merge multiple traffic summaries into one."""
    merged = defaultdict(lambda: {
        'count': 0,
        'user_agents': defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None})
    })

    for summary in summaries:
        for ip, data in summary.items():
            merged[ip]['count'] += data['count']
            for agent, agent_data in data['user_agents'].items():
                merged_agent = merged[ip]['user_agents'][agent]
                merged_agent['count'] += agent_data['count']

                # Track earliest first_seen and latest last_seen
                if merged_agent['first_seen'] is None or agent_data['first_seen'] < merged_agent['first_seen']:
                    merged_agent['first_seen'] = agent_data['first_seen']
                if merged_agent['last_seen'] is None or agent_data['last_seen'] > merged_agent['last_seen']:
                    merged_agent['last_seen'] = agent_data['last_seen']

    return merged


def merge_endpoint_summaries(summaries):
    """Merge multiple endpoint summaries into one."""
    merged = defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None, 'method': None, 'url_type': None})

    for summary in summaries:
        for endpoint, data in summary.items():
            merged_data = merged[endpoint]
            merged_data['count'] += data['count']
            merged_data['method'] = data['method']  # Should be same for all
            merged_data['url_type'] = data['url_type']  # Should be same for all

            # Track earliest first_seen and latest last_seen
            if merged_data['first_seen'] is None or data['first_seen'] < merged_data['first_seen']:
                merged_data['first_seen'] = data['first_seen']
            if merged_data['last_seen'] is None or data['last_seen'] > merged_data['last_seen']:
                merged_data['last_seen'] = data['last_seen']

    return merged


def merge_url_type_summaries(summaries):
    """Merge multiple URL type summaries into one."""
    merged = defaultdict(lambda: {'count': 0, 'first_seen': None, 'last_seen': None, 'method': None})

    for summary in summaries:
        for url_type, data in summary.items():
            merged_data = merged[url_type]
            merged_data['count'] += data['count']
            merged_data['method'] = data['method']  # Should be same for all

            # Track earliest first_seen and latest last_seen
            if merged_data['first_seen'] is None or data['first_seen'] < merged_data['first_seen']:
                merged_data['first_seen'] = data['first_seen']
            if merged_data['last_seen'] is None or data['last_seen'] > merged_data['last_seen']:
                merged_data['last_seen'] = data['last_seen']

    return merged


def process_log_files(log_pattern, ignore_pattern=None):
    """
    Process log files matching a pattern (supports wildcards).
    Returns merged summaries from all matching files.
    """
    # Expand wildcard pattern
    matching_files = sorted(glob.glob(log_pattern))

    if not matching_files:
        print(f"Error: No files matching pattern '{log_pattern}'")
        return None, None, None

    print(f"Found {len(matching_files)} file(s) matching pattern")

    traffic_summaries = []
    endpoint_summaries = []
    url_type_summaries = []

    for log_file in matching_files:
        print(f"  Processing: {log_file}")
        traffic_summary, endpoint_summary, url_type_summary = parse_access_log(log_file, ignore_pattern)

        if traffic_summary:
            traffic_summaries.append(traffic_summary)
            endpoint_summaries.append(endpoint_summary)
            url_type_summaries.append(url_type_summary)
        else:
            print(f"    Warning: Failed to process {log_file}")

    if not traffic_summaries:
        print("Error: No valid logs processed")
        return None, None, None

    # Merge all summaries
    merged_traffic = merge_traffic_summaries(traffic_summaries)
    merged_endpoints = merge_endpoint_summaries(endpoint_summaries)
    merged_url_types = merge_url_type_summaries(url_type_summaries)

    if len(matching_files) > 1:
        print(f"Merged results from {len(matching_files)} file(s)")

    return merged_traffic, merged_endpoints, merged_url_types


# Usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Parse Apache/Nginx access logs and generate traffic summaries by IP, user agent, endpoint, and URL pattern.',
        epilog='''
USAGE EXAMPLES:

  # Single file
  %(prog)s /var/log/apache2/access.log

  # Multiple files with wildcard
  %(prog)s "/var/log/apache2/access*.log"

  # Custom output name
  %(prog)s "/var/log/apache2/access_*.log" -o monthly_summary.csv

OUTPUT FILES:

  When processing access_ssl_log.processed.0.log, access_ssl_log.processed.1.log, etc.,
  all results are merged into single CSV files:

  - monthly_summary.csv              Combined IP/agent analysis
  - monthly_summary_by_agent_type.png     Combined user agent chart
  - monthly_summary_endpoint_summary.csv  Combined endpoints with URL types
  - monthly_summary_url_type_summary.csv  Combined URL patterns

Each summary includes request counts and first/last seen timestamps aggregated
across all matching files.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'log_file',
        help='Path to log file (supports wildcards: access*.log)'
    )
    parser.add_argument(
        '-o', '--output',
        default='traffic_summary.csv',
        help='Output CSV file name (default: traffic_summary.csv)'
    )
    parser.add_argument(
        '-i', '--ignore',
        default=None,
        help='Regex pattern to ignore matching log lines (e.g. "ClaudeBot|SemrushBot")'
    )

    args = parser.parse_args()

    if args.ignore:
        print(f"Ignoring lines matching: {args.ignore}")

    print(f"Processing {args.log_file}...")
    traffic_summary, endpoint_summary, url_type_summary = process_log_files(args.log_file, args.ignore)

    if traffic_summary:
        print_summary(traffic_summary)
        export_to_csv(traffic_summary, args.output)

        # Generate agent type summary graph
        graph_file = args.output.rsplit('.', 1)[0] + '_by_agent_type.png'
        generate_agent_type_graph(traffic_summary, graph_file)

        # Generate country summary graph
        country_graph_file = args.output.rsplit('.', 1)[0] + '_by_country.png'
        generate_country_graph(traffic_summary, country_graph_file)

        # Generate country world heatmap
        country_map_file = args.output.rsplit('.', 1)[0] + '_country_map.png'
        generate_country_map(traffic_summary, country_map_file)

        # Export endpoint summary
        endpoint_file = args.output.rsplit('.', 1)[0] + '_endpoint_summary.csv'
        export_endpoints_to_csv(endpoint_summary, endpoint_file)

        # Export URL type summary
        url_type_file = args.output.rsplit('.', 1)[0] + '_url_type_summary.csv'
        export_url_types_to_csv(url_type_summary, url_type_file)
