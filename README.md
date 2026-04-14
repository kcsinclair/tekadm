# tekadm
A collection of shell scripts and other code to help with Linux and Mac sysadmin.

## Scripts

### `bin/swap.sh`
Shows per-process swap usage on Linux, sorted by usage, plus system-wide swap totals.

```bash
./bin/swap.sh
```

---

### `bin/audit-linux.sh`
Linux security hardening audit script. Checks ~80 controls across 9 categories and reports
`[PASS]` / `[FAIL]` / `[WARN]` / `[INFO]` per check with remediation hints. Read-only — makes no changes.

Based on: **ACSC Essential Eight**, CIS Benchmarks, NIST SP 800-53.

**Categories checked:**
- **SSH Hardening** — root login, password auth, ciphers/MACs, idle timeout, file permissions
- **Users & Authentication** — UID 0 accounts, empty passwords, sudoers NOPASSWD, password policy, account lockout, MFA
- **Filesystem & Permissions** — `/tmp`/`/dev/shm` mount flags, critical file permissions, world-writable files, SUID audit
- **Kernel / sysctl** — ASLR, SYN cookies, reverse path filtering, IP forwarding, ptrace scope, core dumps
- **Firewall** — UFW / firewalld / nftables / iptables detection, default deny policy, listening ports
- **Services** — telnet, FTP, rsh, NIS, avahi, SNMP, time synchronisation
- **Software & Updates** — automatic security updates, pending patches, package signing, compiler tools
- **Logging & Auditing** — auditd, rsyslog, auth log, log rotation, journald persistence
- **AppArmor / SELinux** — enforcement mode active
- **ACSC Essential Eight** — summary mapping to all eight controls

```bash
sudo ./bin/audit-linux.sh        # full results (recommended)
./bin/audit-linux.sh             # partial results without root
```

Exit code `0` if all checks pass, `1` if any failures.

---

### `bin/apache-logs.py`
Apache/Nginx access log analyzer. Parses combined log format (IPv4 and IPv6), classifies user agents,
detects suspect IPs via IPSUM threat intelligence, maps IPs to countries using MaxMind GeoLite2,
and generates CSV reports plus traffic visualizations (bar charts and world heatmap).

See [README-apache-logs.md](README-apache-logs.md) for full documentation.

```bash
python bin/apache-logs.py "/var/log/apache2/access*.log" -o report -i "SemrushBot"
```

---

### `htdocs/api-tester.php`
Standalone PHP CRUD API endpoint for API testing. Token-authenticated, stores data as a JSON file.
Supports create, read, update, delete operations on an animals dataset. Drop onto any PHP web server.

```bash
# Example: create an animal
curl -X POST -H "Authorization: Bearer changeme-secret-token-123" \
  -H "Content-Type: application/json" \
  -d '{"name":"Platypus","count":3,"location":"Queensland","date_seen":"2026-04-14"}' \
  "https://example.com/api-tester.php?action=create"
```

---

## Setup

```bash
./install.sh          # fixes bin/ permissions and adds tekadm/bin to your shell PATH
source ./init.sh      # or manually add to ~/.bashrc / ~/.zshrc
```

