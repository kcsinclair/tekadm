#!/usr/bin/env python3
"""
Tests for apache-logs.py log line parsing.

Each entry in TEST_LINES is a (description, log_line, expected) tuple.
  - expected is a dict of group names the regex should capture, or None if
    the line should be skipped (blank / comment).

Run:  python3 -m pytest test/test_parse_log_lines.py -v
  or: python3 test/test_parse_log_lines.py
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import the regex from apache-logs.py by adding bin/ to the path
# We reconstruct the pattern here so the test is self-contained and can also
# serve as a specification for what the regex *should* match.
# ---------------------------------------------------------------------------

# Add the project root so we can locate bin/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "bin"))


def _get_log_pattern():
    """Build the log_pattern regex the same way apache-logs.py does."""
    # Import directly from the script to test the actual code
    # We read the compiled regex from parse_access_log's source instead,
    # since the function is not easily callable for just the regex.
    # Instead, replicate it here — if the script changes, update this too.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "apache_logs", PROJECT_ROOT / "bin" / "apache-logs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # We don't exec the module (it has side effects via argparse at bottom).
    # Instead, just read the source and extract what we need.
    # Simpler: define the pattern directly and keep it in sync.
    return None  # not used — we test the live script via subprocess


# ---------------------------------------------------------------------------
# Compile the regex pattern — must match bin/apache-logs.py log_pattern
# ---------------------------------------------------------------------------
LOG_PATTERN = re.compile(
    r'(\d+\.\d+\.\d+\.\d+|'           # IPv4 address  OR
    r'\[?[0-9a-fA-F:]+\]?)\s+'         # IPv6 address (with or without brackets)
    r'.*?\[([^\]]+)\]\s+'              # Timestamp
    r'"([A-Z]+\s+\S+\s+\S+)"\s+'      # Request (method path protocol)
    r'(\d+)\s+'                         # Status code
    r'(\d+|-)\s+'                       # Bytes sent
    r'"((?:[^"\\]|\\.)*)"\s+'          # Referer  (allows escaped quotes)
    r'"((?:[^"\\]|\\.)*)"'             # User agent (allows escaped quotes)
)

# Group indices (1-based)
GRP_IP = 1
GRP_TIMESTAMP = 2
GRP_REQUEST = 3
GRP_STATUS = 4
GRP_BYTES = 5
GRP_REFERER = 6
GRP_USERAGENT = 7


# ---------------------------------------------------------------------------
# Test cases — add new entries here when you find unparseable lines
# ---------------------------------------------------------------------------
TEST_LINES = [
    # --- Standard IPv4 lines ---
    (
        "standard IPv4 GET request",
        '172.64.198.135 - - [22/Mar/2026:21:17:29 +0000] "GET /volunteers-programs/ HTTP/1.1" 200 12911 "-" '
        '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"',
        {
            GRP_IP: "172.64.198.135",
            GRP_STATUS: "200",
            GRP_BYTES: "12911",
            GRP_REFERER: "-",
        },
    ),

    # --- Bare IPv6 (no brackets) ---
    (
        "bare IPv6 address (no brackets)",
        '2001:41d0:303:b76a::1 - - [04/Apr/2026:12:14:49 +0000] "GET /robots.txt HTTP/1.1" 200 3578 "-" '
        '"Mozilla/5.0 (compatible; MJ12bot/v1.4.8; http://mj12bot.com/)"',
        {
            GRP_IP: "2001:41d0:303:b76a::1",
            GRP_STATUS: "200",
            GRP_BYTES: "3578",
        },
    ),
    (
        "bare IPv6 address (short form)",
        '2400:cb00:601:1000:dd6c:bbed:2e8e:9b7 - - [31/Mar/2026:15:41:57 +0000] "GET /hostgator.zip HTTP/1.1" 302 552 "-" '
        '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"',
        {
            GRP_IP: "2400:cb00:601:1000:dd6c:bbed:2e8e:9b7",
            GRP_STATUS: "302",
        },
    ),

    # --- Bracketed IPv6 (already supported) ---
    (
        "bracketed IPv6 address",
        '[2400:cb00:548:1000:4725:8fb3:735e:7194] - - [13/Mar/2026:14:07:06 +0000] "GET /page HTTP/1.1" 200 1234 "-" "TestAgent"',
        {
            GRP_IP: "[2400:cb00:548:1000:4725:8fb3:735e:7194]",
            GRP_STATUS: "200",
        },
    ),

    # --- Escaped quotes in referer ---
    (
        "escaped double-quote in referer field",
        '172.64.198.135 - - [22/Mar/2026:21:18:41 +0000] "GET /about-fraser-island/fauna/ HTTP/1.1" 200 14737 "https://fido.org.au/.(,\'.),((\\"" "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"',
        {
            GRP_IP: "172.64.198.135",
            GRP_STATUS: "200",
            GRP_BYTES: "14737",
        },
    ),

    # --- Bytes field is "-" ---
    (
        "bytes sent is dash (redirect with no body)",
        '10.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET /redirect HTTP/1.1" 301 - "-" "curl/7.88.1"',
        {
            GRP_IP: "10.0.0.1",
            GRP_STATUS: "301",
            GRP_BYTES: "-",
        },
    ),
]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
def test_all_lines_parse():
    """Every TEST_LINES entry with a non-None expected dict must match."""
    failures = []
    for desc, line, expected in TEST_LINES:
        if expected is None:
            continue
        m = LOG_PATTERN.search(line)
        if m is None:
            failures.append(f"FAIL  [{desc}]: regex did not match")
            continue
        for grp, want in expected.items():
            got = m.group(grp)
            if got != want:
                failures.append(
                    f"FAIL  [{desc}]: group {grp} expected {want!r}, got {got!r}"
                )

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        raise AssertionError(
            f"{len(failures)} parsing failure(s):\n" + "\n".join(failures)
        )


def test_blank_lines_skip():
    """Blank / whitespace-only lines should not match."""
    for line in ["", "   ", "\n", "\t\n"]:
        assert LOG_PATTERN.search(line) is None, f"Blank line matched: {line!r}"


def test_log_file_no_unparsed(tmp_path):
    """Run the actual script on test-apache.log and assert zero 'Could not parse' warnings."""
    import subprocess
    log_file = PROJECT_ROOT / "test" / "test-apache.log"
    if not log_file.exists():
        return  # skip if log file not present
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "bin" / "apache-logs.py"), str(log_file)],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    output = result.stdout + result.stderr
    unparsed = [
        l for l in output.splitlines()
        if "Could not parse" in l and not l.strip().endswith(":")
    ]
    if unparsed:
        raise AssertionError(
            f"{len(unparsed)} unparsed line(s) in test-apache.log:\n"
            + "\n".join(unparsed[:20])
        )


# ---------------------------------------------------------------------------
# Allow running directly: python3 test/test_parse_log_lines.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running log line parse tests...\n")
    passed = 0
    failed = 0

    for name, func in [
        ("test_all_lines_parse", test_all_lines_parse),
        ("test_blank_lines_skip", test_blank_lines_skip),
    ]:
        try:
            func()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1

    # Run the log-file integration test without pytest's tmp_path
    try:
        test_log_file_no_unparsed(None)
        print(f"  PASS  test_log_file_no_unparsed")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL  test_log_file_no_unparsed: {e}")
        failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
