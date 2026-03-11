#!/usr/bin/env bash
# audit.sh — Linux security hardening audit
# Checks common hardening controls and reports PASS/FAIL/WARN per check.
# Run as root for complete results. Read-only — makes no changes.
#
# Sources: ACSC Essential Eight, CIS Benchmarks, NIST SP 800-53, CIS Linux

set -uo pipefail

# ---------------------------------------------------------------------------
# OS CHECK
# ---------------------------------------------------------------------------
if [ "$(uname -s)" != "Linux" ]; then
    echo "ERROR: This script only supports Linux. Detected: $(uname -s)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# DISTRO DETECTION
# ---------------------------------------------------------------------------
DISTRO_FAMILY="unknown"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "${ID_LIKE:-} ${ID:-}" in
        *debian*|*ubuntu*) DISTRO_FAMILY="debian" ;;
        *rhel*|*fedora*|*centos*|*amzn*) DISTRO_FAMILY="rhel" ;;
    esac
fi

# ---------------------------------------------------------------------------
# COLOR SETUP
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
    GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
else
    GREEN=''; RED=''; YELLOW=''; BLUE=''; BOLD=''; NC=''
fi

# ---------------------------------------------------------------------------
# COUNTERS & HELPERS
# ---------------------------------------------------------------------------
PASS=0; FAIL=0; WARN=0; INFO_COUNT=0

pass()  { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS++)); }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL++)); }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; ((WARN++)); }
info()  { echo -e "${BLUE}[INFO]${NC} $1"; ((INFO_COUNT++)); }
header(){ echo; echo -e "${BOLD}$(printf '=%.0s' {1..56})${NC}"; echo -e "${BOLD}  $1${NC}"; echo -e "${BOLD}$(printf '=%.0s' {1..56})${NC}"; }

sysctl_val() { sysctl -n "$1" 2>/dev/null || echo ""; }

is_service_active() { systemctl is-active --quiet "$1" 2>/dev/null; }
is_service_enabled() { systemctl is-enabled --quiet "$1" 2>/dev/null; }

# ---------------------------------------------------------------------------
# ROOT CHECK
# ---------------------------------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo -e "${YELLOW}NOTE: Not running as root. Some checks will be skipped or incomplete.${NC}"
        echo -e "${YELLOW}      Re-run with: sudo $0${NC}"
        echo
    fi
}

# ---------------------------------------------------------------------------
# 1. SSH HARDENING
# ---------------------------------------------------------------------------
check_ssh() {
    header "SSH HARDENING"

    if ! command -v sshd &>/dev/null; then
        info "sshd not installed — skipping SSH checks"
        return
    fi

    local ssh_config
    ssh_config=$(sshd -T 2>/dev/null)
    if [ -z "$ssh_config" ]; then
        warn "Could not read sshd effective config (sshd -T failed)"
        return
    fi

    ssh_val() { echo "$ssh_config" | grep -i "^$1 " | awk '{print $2}' | head -1; }

    # Root login
    local v
    v=$(ssh_val permitrootlogin)
    [ "$v" = "no" ] && pass "Root login disabled" || fail "Root login not disabled (permitrootlogin=$v)  →  Set: PermitRootLogin no"

    # Password auth
    v=$(ssh_val passwordauthentication)
    [ "$v" = "no" ] && pass "Password authentication disabled (keys only)" || fail "Password auth enabled (passwordauthentication=$v)  →  Set: PasswordAuthentication no"

    # Empty passwords
    v=$(ssh_val permitemptypasswords)
    [ "$v" = "no" ] && pass "Empty passwords disallowed" || fail "Empty passwords may be allowed  →  Set: PermitEmptyPasswords no"

    # X11 forwarding
    v=$(ssh_val x11forwarding)
    [ "$v" = "no" ] && pass "X11 forwarding disabled" || fail "X11 forwarding enabled  →  Set: X11Forwarding no"

    # LoginGraceTime
    v=$(ssh_val logingracetime)
    if [ -n "$v" ] && [ "$v" -le 60 ] 2>/dev/null; then
        pass "LoginGraceTime is ${v}s (≤ 60)"
    else
        warn "LoginGraceTime is ${v:-default} (> 60 or unset)  →  Set: LoginGraceTime 60"
    fi

    # MaxAuthTries
    v=$(ssh_val maxauthtries)
    if [ -n "$v" ] && [ "$v" -le 4 ] 2>/dev/null; then
        pass "MaxAuthTries is $v (≤ 4)"
    else
        warn "MaxAuthTries is ${v:-default 6}  →  Set: MaxAuthTries 4"
    fi

    # ClientAliveInterval (idle timeout)
    v=$(ssh_val clientaliveinterval)
    if [ -n "$v" ] && [ "$v" -gt 0 ] && [ "$v" -le 300 ] 2>/dev/null; then
        pass "SSH idle timeout set (ClientAliveInterval=${v}s)"
    else
        warn "SSH idle timeout not configured or too long (ClientAliveInterval=${v:-0})  →  Set: ClientAliveInterval 300 / ClientAliveCountMax 3"
    fi

    # IgnoreRhosts
    v=$(ssh_val ignorerhosts)
    [ "$v" = "yes" ] && pass "Rhosts ignored" || warn "IgnoreRhosts not yes (=$v)  →  Set: IgnoreRhosts yes"

    # HostbasedAuthentication
    v=$(ssh_val hostbasedauthentication)
    [ "$v" = "no" ] && pass "Host-based authentication disabled" || fail "Host-based authentication enabled  →  Set: HostbasedAuthentication no"

    # Weak ciphers
    local ciphers
    ciphers=$(ssh_val ciphers)
    if echo "$ciphers" | grep -qiE 'arcfour|3des|blowfish|rc4'; then
        fail "Weak ciphers present: $ciphers  →  Remove arcfour/3des/blowfish from Ciphers"
    else
        pass "No weak ciphers detected"
    fi

    # Weak MACs
    local macs
    macs=$(ssh_val macs)
    if echo "$macs" | grep -qiE 'hmac-md5|hmac-sha1-96'; then
        fail "Weak MACs present: $macs  →  Remove hmac-md5 and hmac-sha1-96 from MACs in sshd_config"
    else
        pass "No weak MACs detected"
    fi

    # sshd_config permissions
    if [ -f /etc/ssh/sshd_config ]; then
        local perms owner
        perms=$(stat -c "%a" /etc/ssh/sshd_config 2>/dev/null)
        owner=$(stat -c "%U" /etc/ssh/sshd_config 2>/dev/null)
        if [ "$perms" = "600" ] && [ "$owner" = "root" ]; then
            pass "sshd_config permissions are 600 root"
        else
            fail "sshd_config permissions: ${perms} ${owner} (expected 600 root)  →  chmod 600 /etc/ssh/sshd_config"
        fi
    fi

    # SSH host private key permissions
    local key_fail=0
    while IFS= read -r -d '' keyfile; do
        local kperms
        kperms=$(stat -c "%a" "$keyfile" 2>/dev/null)
        [ "$kperms" != "600" ] && key_fail=1
    done < <(find /etc/ssh -name 'ssh_host_*_key' ! -name '*.pub' -print0 2>/dev/null)
    if [ "$key_fail" -eq 0 ]; then
        pass "SSH host private keys are mode 600"
    else
        fail "SSH host private key(s) not mode 600  →  chmod 600 /etc/ssh/ssh_host_*_key"
    fi
}

# ---------------------------------------------------------------------------
# 2. USERS & AUTHENTICATION
# ---------------------------------------------------------------------------
check_users() {
    header "USERS & AUTHENTICATION"

    # UID 0 accounts other than root
    local uid0
    uid0=$(awk -F: '($3 == 0) { print $1 }' /etc/passwd | grep -v '^root$' || true)
    if [ -z "$uid0" ]; then
        pass "Only root has UID 0"
    else
        fail "Non-root accounts with UID 0: $uid0  →  Investigate immediately"
    fi

    # Empty password field in /etc/shadow
    if [ -r /etc/shadow ]; then
        local empty_pw
        empty_pw=$(awk -F: '($2 == "") { print $1 }' /etc/shadow || true)
        if [ -z "$empty_pw" ]; then
            pass "No accounts with empty password hash"
        else
            fail "Accounts with empty password: $empty_pw  →  Lock or set passwords"
        fi
    else
        info "Cannot read /etc/shadow (requires root) — empty password check skipped"
    fi

    # sudoers NOPASSWD
    if [ -r /etc/sudoers ]; then
        local nopasswd
        nopasswd=$(grep -rh 'NOPASSWD' /etc/sudoers /etc/sudoers.d/ 2>/dev/null | grep -v '^#' || true)
        if [ -z "$nopasswd" ]; then
            pass "No NOPASSWD entries in sudoers"
        else
            warn "NOPASSWD found in sudoers — review if intentional:$(echo; echo "$nopasswd" | sed 's/^/    /')"
        fi

        # sudoers permissions
        local sperms sowner
        sperms=$(stat -c "%a" /etc/sudoers 2>/dev/null)
        sowner=$(stat -c "%U" /etc/sudoers 2>/dev/null)
        if [ "$sperms" = "440" ] && [ "$sowner" = "root" ]; then
            pass "sudoers permissions are 440 root"
        else
            fail "sudoers permissions: ${sperms} ${sowner} (expected 440 root)  →  chmod 440 /etc/sudoers"
        fi
    else
        info "Cannot read /etc/sudoers (requires root) — sudoers checks skipped"
    fi

    # Password max days
    if [ -f /etc/login.defs ]; then
        local max_days
        max_days=$(grep -E '^PASS_MAX_DAYS' /etc/login.defs | awk '{print $2}')
        if [ -n "$max_days" ] && [ "$max_days" -le 90 ] 2>/dev/null; then
            pass "PASS_MAX_DAYS is $max_days (≤ 90)"
        else
            warn "PASS_MAX_DAYS is ${max_days:-unset}  →  Set PASS_MAX_DAYS 90 in /etc/login.defs"
        fi

        # Password min days
        local min_days
        min_days=$(grep -E '^PASS_MIN_DAYS' /etc/login.defs | awk '{print $2}')
        if [ -n "$min_days" ] && [ "$min_days" -ge 1 ] 2>/dev/null; then
            pass "PASS_MIN_DAYS is $min_days (≥ 1)"
        else
            warn "PASS_MIN_DAYS is ${min_days:-unset}  →  Set PASS_MIN_DAYS 1 in /etc/login.defs"
        fi

        # Default umask
        local umask_val
        umask_val=$(grep -E '^UMASK' /etc/login.defs | awk '{print $2}')
        if [ -n "$umask_val" ] && [ "$umask_val" -le 27 ] 2>/dev/null; then
            pass "Default UMASK is $umask_val (≤ 027)"
        else
            warn "UMASK is ${umask_val:-unset}  →  Set UMASK 027 in /etc/login.defs"
        fi
    fi

    # Account lockout (pam_faillock or pam_tally2)
    if grep -rl 'pam_faillock\|pam_tally2' /etc/pam.d/ &>/dev/null; then
        pass "Account lockout configured (pam_faillock or pam_tally2)"
    else
        fail "No account lockout policy found  →  Configure pam_faillock in /etc/pam.d/common-auth"
    fi

    # Root home dir permissions
    local rperms
    rperms=$(stat -c "%a" /root 2>/dev/null)
    if [ "$rperms" = "700" ]; then
        pass "Root home directory is mode 700"
    else
        fail "Root home directory is mode $rperms (expected 700)  →  chmod 700 /root"
    fi

    # MFA check (Essential Eight)
    if grep -rl 'pam_google_authenticator\|pam_duo\|pam_radius\|pam_oath\|pam_u2f' /etc/pam.d/ &>/dev/null; then
        pass "MFA module detected in PAM configuration"
    else
        warn "No MFA module found in /etc/pam.d/  →  Consider pam_google_authenticator or pam_duo for SSH/sudo (Essential Eight)"
    fi
}

# ---------------------------------------------------------------------------
# 3. FILESYSTEM & PERMISSIONS
# ---------------------------------------------------------------------------
check_filesystem() {
    header "FILESYSTEM & PERMISSIONS"

    # /tmp mount options
    for opt in noexec nosuid nodev; do
        if findmnt -n -o OPTIONS /tmp 2>/dev/null | grep -q "$opt"; then
            pass "/tmp mounted with $opt"
        else
            warn "/tmp not mounted with $opt  →  Add $opt to /tmp in /etc/fstab"
        fi
    done

    # /dev/shm mount options
    for opt in noexec nosuid nodev; do
        if findmnt -n -o OPTIONS /dev/shm 2>/dev/null | grep -q "$opt"; then
            pass "/dev/shm mounted with $opt"
        else
            warn "/dev/shm not mounted with $opt  →  Add $opt to /dev/shm in /etc/fstab"
        fi
    done

    # Critical file permissions
    check_file_perms() {
        local file="$1" expected_mode="$2" expected_owner="$3" expected_group="$4"
        if [ ! -e "$file" ]; then return; fi
        local mode owner group
        mode=$(stat -c "%a" "$file" 2>/dev/null)
        owner=$(stat -c "%U" "$file" 2>/dev/null)
        group=$(stat -c "%G" "$file" 2>/dev/null)
        if [ "$mode" = "$expected_mode" ] && [ "$owner" = "$expected_owner" ] && [ "$group" = "$expected_group" ]; then
            pass "$file permissions: $mode $owner:$group"
        else
            fail "$file permissions: $mode $owner:$group (expected $expected_mode $expected_owner:$expected_group)  →  chmod $expected_mode $file"
        fi
    }

    check_file_perms /etc/passwd  644 root root
    check_file_perms /etc/group   644 root root
    if [ -f /etc/shadow ]; then
        local sm so sg
        sm=$(stat -c "%a" /etc/shadow 2>/dev/null)
        so=$(stat -c "%U" /etc/shadow 2>/dev/null)
        sg=$(stat -c "%G" /etc/shadow 2>/dev/null)
        if [[ "$sm" =~ ^(0|640)$ ]] && [ "$so" = "root" ]; then
            pass "/etc/shadow permissions: $sm $so:$sg"
        else
            fail "/etc/shadow permissions: $sm $so:$sg (expected 000 or 640 root)  →  chmod 640 /etc/shadow; chown root:shadow /etc/shadow"
        fi
    fi

    # World-writable files (excluding /proc /sys /run)
    echo -n "  Scanning for world-writable files..."
    local ww_files
    ww_files=$(find / -xdev -type f -perm -0002 2>/dev/null | grep -vE '^/(proc|sys|run)' || true)
    echo " done"
    if [ -z "$ww_files" ]; then
        pass "No unexpected world-writable files found"
    else
        local ww_count
        ww_count=$(echo "$ww_files" | wc -l)
        warn "$ww_count world-writable file(s) found  →  Review and remove write permission where not needed:"
        echo "$ww_files" | head -10 | sed 's/^/    /'
        [ "$ww_count" -gt 10 ] && echo "    ... and $((ww_count - 10)) more"
    fi

    # World-writable dirs without sticky bit
    local ww_dirs
    ww_dirs=$(find / -xdev -type d -perm -0002 ! -perm -1000 2>/dev/null | grep -vE '^/(proc|sys|run)' || true)
    if [ -z "$ww_dirs" ]; then
        pass "All world-writable directories have sticky bit set"
    else
        fail "World-writable directories without sticky bit:$(echo; echo "$ww_dirs" | sed 's/^/    /')  →  chmod +t <dir>"
    fi

    # SUID files — list for review (not auto-fail)
    echo -n "  Scanning for SUID binaries..."
    local suid_files
    suid_files=$(find / -xdev -type f -perm -4000 2>/dev/null | grep -vE '^/(proc|sys)' | sort || true)
    echo " done"
    local suid_count
    suid_count=$(echo "$suid_files" | grep -c . || true)
    info "SUID binaries found ($suid_count) — review for unexpected entries:"
    echo "$suid_files" | sed 's/^/    /'

    # Unowned files
    echo -n "  Scanning for unowned files..."
    local unowned
    unowned=$(find / -xdev \( -nouser -o -nogroup \) 2>/dev/null | grep -vE '^/(proc|sys)' || true)
    echo " done"
    if [ -z "$unowned" ]; then
        pass "No unowned files found"
    else
        warn "Unowned files found:$(echo; echo "$unowned" | head -10 | sed 's/^/    /')  →  Investigate and assign ownership"
    fi
}

# ---------------------------------------------------------------------------
# 4. KERNEL / SYSCTL
# ---------------------------------------------------------------------------
check_sysctl() {
    header "KERNEL / SYSCTL HARDENING"

    sysctl_check() {
        local key="$1" expected="$2" op="${3:-eq}" label="$4" fix="$5"
        local val
        val=$(sysctl_val "$key")
        if [ -z "$val" ]; then
            warn "$key not available on this kernel"
            return
        fi
        local ok=0
        case "$op" in
            eq)  [ "$val" = "$expected" ] && ok=1 ;;
            ge)  [ "$val" -ge "$expected" ] 2>/dev/null && ok=1 ;;
        esac
        if [ "$ok" -eq 1 ]; then
            pass "$label ($key = $val)"
        else
            fail "$label ($key = $val, expected $expected)  →  $fix"
        fi
    }

    sysctl_check net.ipv4.ip_forward               0  eq "IP forwarding disabled"                   "sysctl -w net.ipv4.ip_forward=0"
    sysctl_check net.ipv4.conf.all.accept_redirects 0  eq "ICMP redirects not accepted"              "sysctl -w net.ipv4.conf.all.accept_redirects=0"
    sysctl_check net.ipv4.conf.all.send_redirects   0  eq "ICMP redirects not sent"                  "sysctl -w net.ipv4.conf.all.send_redirects=0"
    sysctl_check net.ipv4.conf.all.accept_source_route 0 eq "IP source routing disabled"             "sysctl -w net.ipv4.conf.all.accept_source_route=0"
    sysctl_check net.ipv4.tcp_syncookies            1  eq "TCP SYN cookies enabled (SYN flood protection)" "sysctl -w net.ipv4.tcp_syncookies=1"
    sysctl_check net.ipv4.conf.all.rp_filter        1  ge "Reverse path filtering enabled"           "sysctl -w net.ipv4.conf.all.rp_filter=1"
    sysctl_check kernel.randomize_va_space          2  eq "ASLR fully enabled"                        "sysctl -w kernel.randomize_va_space=2"
    sysctl_check fs.suid_dumpable                   0  eq "SUID core dumps disabled"                  "sysctl -w fs.suid_dumpable=0"
    sysctl_check kernel.dmesg_restrict              1  eq "dmesg restricted to root"                  "sysctl -w kernel.dmesg_restrict=1"
    sysctl_check kernel.yama.ptrace_scope           1  ge "ptrace scope restricted"                   "sysctl -w kernel.yama.ptrace_scope=1"
    sysctl_check net.ipv4.conf.all.log_martians     1  eq "Martian packets logged"                    "sysctl -w net.ipv4.conf.all.log_martians=1"
    sysctl_check net.ipv4.icmp_ignore_bogus_error_responses 1 eq "Bogus ICMP responses ignored"       "sysctl -w net.ipv4.icmp_ignore_bogus_error_responses=1"

    # Check persistence in sysctl config files
    if grep -rqE '(syncookies|rp_filter|randomize_va_space)' /etc/sysctl.conf /etc/sysctl.d/ 2>/dev/null; then
        pass "sysctl hardening persisted in /etc/sysctl.conf or /etc/sysctl.d/"
    else
        warn "sysctl parameters may not persist across reboots  →  Add settings to /etc/sysctl.d/99-hardening.conf"
    fi
}

# ---------------------------------------------------------------------------
# 5. FIREWALL
# ---------------------------------------------------------------------------
check_firewall() {
    header "FIREWALL"

    local fw_found=0

    # UFW
    if command -v ufw &>/dev/null; then
        local ufw_status
        ufw_status=$(ufw status 2>/dev/null | head -1)
        if echo "$ufw_status" | grep -q "Status: active"; then
            pass "UFW is active"
            fw_found=1
            is_service_enabled ufw && pass "UFW enabled at boot" || fail "UFW not enabled at boot  →  systemctl enable ufw"
            # Default deny incoming
            if ufw status verbose 2>/dev/null | grep -q "Default:.*deny.*incoming"; then
                pass "UFW default incoming policy: deny"
            else
                fail "UFW default incoming policy is not deny  →  ufw default deny incoming"
            fi
        fi
    fi

    # firewalld
    if command -v firewall-cmd &>/dev/null && firewall-cmd --state &>/dev/null 2>&1 | grep -q running; then
        pass "firewalld is running"
        fw_found=1
        is_service_enabled firewalld && pass "firewalld enabled at boot" || fail "firewalld not enabled at boot  →  systemctl enable firewalld"
    fi

    # nftables
    if command -v nft &>/dev/null; then
        local nft_rules
        nft_rules=$(nft list ruleset 2>/dev/null | grep -c 'rule' || true)
        if [ "${nft_rules:-0}" -gt 0 ]; then
            pass "nftables has $nft_rules rule(s) configured"
            fw_found=1
        fi
    fi

    # iptables fallback
    if command -v iptables &>/dev/null && [ "$fw_found" -eq 0 ]; then
        local ipt_policy
        ipt_policy=$(iptables -L INPUT -n 2>/dev/null | grep 'Chain INPUT' | grep -oE '\(policy [A-Z]+\)' | tr -d '()')
        if echo "$ipt_policy" | grep -qE 'DROP|REJECT'; then
            pass "iptables INPUT default policy is DROP/REJECT"
            fw_found=1
        else
            fail "iptables INPUT policy is not DROP/REJECT (=$ipt_policy)  →  iptables -P INPUT DROP"
        fi
    fi

    [ "$fw_found" -eq 0 ] && fail "No active firewall detected  →  Install and configure ufw, firewalld, or nftables"

    # Listening ports for review
    echo
    info "Listening TCP ports (review for unexpected services):"
    ss -tlnp 2>/dev/null | grep LISTEN | sed 's/^/    /' || netstat -tlnp 2>/dev/null | sed 's/^/    /'
}

# ---------------------------------------------------------------------------
# 6. SERVICES
# ---------------------------------------------------------------------------
check_services() {
    header "SERVICES"

    # Dangerous/legacy services that should NOT be running
    insecure_service_check() {
        local name="$1"
        if is_service_active "$name" 2>/dev/null; then
            fail "Insecure service is running: $name  →  systemctl disable --now $name"
        else
            pass "$name is not running"
        fi
    }

    insecure_service_check telnet.socket
    insecure_service_check telnetd
    insecure_service_check vsftpd
    insecure_service_check proftpd
    insecure_service_check pure-ftpd
    insecure_service_check rsh.socket
    insecure_service_check rlogin.socket
    insecure_service_check rexec.socket
    insecure_service_check ypserv
    insecure_service_check ypbind
    insecure_service_check inetd
    insecure_service_check xinetd
    insecure_service_check avahi-daemon

    # SNMP — warn if active, check for default community strings
    if is_service_active snmpd 2>/dev/null; then
        warn "snmpd is running — verify it is needed and secured"
        if grep -qiE 'community (public|private)' /etc/snmp/snmpd.conf 2>/dev/null; then
            fail "snmpd using default community strings (public/private)  →  Change in /etc/snmp/snmpd.conf"
        fi
    else
        pass "snmpd is not running"
    fi

    # Time synchronization should be active
    local time_sync=0
    for svc in ntp chrony chronyd systemd-timesyncd; do
        is_service_active "$svc" 2>/dev/null && time_sync=1 && break
    done
    if [ "$time_sync" -eq 1 ]; then
        pass "Time synchronization service is active"
    else
        fail "No time synchronization service is active  →  systemctl enable --now systemd-timesyncd"
    fi
}

# ---------------------------------------------------------------------------
# 7. SOFTWARE & UPDATES
# ---------------------------------------------------------------------------
check_updates() {
    header "SOFTWARE & UPDATES"

    case "$DISTRO_FAMILY" in
        debian)
            if dpkg -l unattended-upgrades 2>/dev/null | grep -q '^ii'; then
                pass "unattended-upgrades package is installed"
                if is_service_active unattended-upgrades 2>/dev/null || \
                   systemctl is-active --quiet apt-daily-upgrade.timer 2>/dev/null; then
                    pass "Automatic security updates are active"
                else
                    warn "unattended-upgrades installed but service may not be active  →  Check /etc/apt/apt.conf.d/50unattended-upgrades"
                fi
            else
                fail "unattended-upgrades not installed  →  apt install unattended-upgrades && dpkg-reconfigure unattended-upgrades"
            fi

            # Pending security updates
            local sec_count
            sec_count=$(apt list --upgradable 2>/dev/null | grep -ic security || true)
            if [ "$sec_count" -eq 0 ]; then
                pass "No pending security updates"
            else
                fail "$sec_count pending security update(s)  →  apt upgrade"
            fi
            ;;
        rhel)
            if systemctl is-active --quiet dnf-automatic.timer 2>/dev/null || \
               systemctl is-active --quiet yum-cron 2>/dev/null; then
                pass "Automatic updates are active (dnf-automatic or yum-cron)"
            else
                warn "No automatic update timer found  →  dnf install dnf-automatic && systemctl enable --now dnf-automatic.timer"
            fi

            # gpgcheck
            if grep -rqE '^gpgcheck\s*=\s*0' /etc/yum.repos.d/ /etc/yum.conf 2>/dev/null; then
                fail "Some yum/dnf repos have gpgcheck=0  →  Set gpgcheck=1 in all repo files"
            else
                pass "Package signature checking (gpgcheck) enabled in all repos"
            fi
            ;;
        *)
            info "Unknown distro family — skipping distro-specific update checks"
            ;;
    esac

    # Compiler tools on production server
    local compilers=()
    for tool in gcc g++ cc make; do
        command -v "$tool" &>/dev/null && compilers+=("$tool")
    done
    if [ "${#compilers[@]}" -eq 0 ]; then
        pass "No compiler tools (gcc/make) found on system"
    else
        warn "Compiler tools present: ${compilers[*]}  →  Remove from production servers to reduce attack surface"
    fi
}

# ---------------------------------------------------------------------------
# 8. LOGGING & AUDITING
# ---------------------------------------------------------------------------
check_logging() {
    header "LOGGING & AUDITING"

    # auditd
    if command -v auditd &>/dev/null || dpkg -l auditd &>/dev/null 2>&1 | grep -q '^ii' || rpm -q audit &>/dev/null 2>&1; then
        pass "auditd package is installed"
        if is_service_active auditd; then
            pass "auditd is running"
        else
            fail "auditd is not running  →  systemctl enable --now auditd"
        fi
        is_service_enabled auditd && pass "auditd enabled at boot" || fail "auditd not enabled at boot  →  systemctl enable auditd"

        # Audit rules
        local rule_count
        rule_count=$(auditctl -l 2>/dev/null | grep -vc '^-a\|^-w' || auditctl -l 2>/dev/null | wc -l || echo "0")
        local total_rules
        total_rules=$(auditctl -l 2>/dev/null | wc -l 2>/dev/null || echo "0")
        if [ "${total_rules:-0}" -gt 1 ]; then
            pass "auditd rules configured ($total_rules rules)"
        else
            warn "auditd has no rules configured  →  Add rules to /etc/audit/rules.d/"
        fi
    else
        fail "auditd not installed  →  apt install auditd / dnf install audit"
    fi

    # rsyslog or syslog-ng
    if is_service_active rsyslog 2>/dev/null || is_service_active syslog-ng 2>/dev/null; then
        pass "Syslog service (rsyslog or syslog-ng) is active"
    else
        fail "No syslog service running  →  systemctl enable --now rsyslog"
    fi

    # Auth log
    local auth_log
    auth_log=""
    [ -f /var/log/auth.log ] && auth_log="/var/log/auth.log"
    [ -f /var/log/secure ]   && auth_log="/var/log/secure"
    if [ -n "$auth_log" ]; then
        # Check if written to in last 24 hours
        if find "$auth_log" -mtime -1 2>/dev/null | grep -q .; then
            pass "Auth log ($auth_log) is being written to"
        else
            warn "Auth log ($auth_log) has not been written to in 24h"
        fi
    else
        warn "No auth log found (/var/log/auth.log or /var/log/secure)"
    fi

    # Log rotation
    local lr_count
    lr_count=$(ls /etc/logrotate.d/ 2>/dev/null | wc -l)
    if [ "${lr_count:-0}" -gt 0 ]; then
        pass "Log rotation configured ($lr_count logrotate.d entries)"
    else
        warn "No logrotate.d entries found  →  Configure log rotation"
    fi

    # journald persistent storage
    if grep -qi 'Storage=persistent' /etc/systemd/journald.conf 2>/dev/null; then
        pass "journald configured for persistent storage"
    else
        warn "journald may not use persistent storage  →  Set Storage=persistent in /etc/systemd/journald.conf"
    fi
}

# ---------------------------------------------------------------------------
# 9. APPARMOR / SELINUX
# ---------------------------------------------------------------------------
check_mac() {
    header "MANDATORY ACCESS CONTROL (AppArmor / SELinux)"

    local mac_active=0

    # AppArmor
    if command -v apparmor_status &>/dev/null || command -v aa-status &>/dev/null; then
        local aa_cmd
        aa_cmd=$(command -v apparmor_status || command -v aa-status)
        local enforce_count
        enforce_count=$("$aa_cmd" 2>/dev/null | grep 'profiles are in enforce mode' | awk '{print $1}' || echo "0")
        if [ "${enforce_count:-0}" -gt 0 ]; then
            pass "AppArmor active: $enforce_count profile(s) in enforce mode"
            mac_active=1
        else
            warn "AppArmor present but no profiles enforcing  →  aa-enforce /etc/apparmor.d/*"
        fi
    fi

    # SELinux
    if command -v getenforce &>/dev/null; then
        local se_mode
        se_mode=$(getenforce 2>/dev/null)
        if [ "$se_mode" = "Enforcing" ]; then
            pass "SELinux is Enforcing"
            mac_active=1
        elif [ "$se_mode" = "Permissive" ]; then
            warn "SELinux is Permissive (not enforcing)  →  setenforce 1 and set SELINUX=enforcing in /etc/selinux/config"
        else
            info "SELinux status: ${se_mode:-unavailable}"
        fi
    fi

    [ "$mac_active" -eq 0 ] && fail "No Mandatory Access Control framework is enforcing  →  Enable AppArmor or SELinux"
}

# ---------------------------------------------------------------------------
# 10. ESSENTIAL EIGHT (ACSC)
# ---------------------------------------------------------------------------
check_essential_eight() {
    header "ACSC ESSENTIAL EIGHT — SUMMARY"

    echo "  Mapping to Australian Cyber Security Centre Essential Eight controls:"
    echo

    e8_item() { echo -e "  ${BOLD}$1${NC} — $2"; }

    e8_item "1. Patch Applications"         "See: Software & Updates section above"
    e8_item "2. Patch Operating System"     "Run: apt list --upgradable / dnf check-update"
    e8_item "3. Multi-Factor Authentication" "Check: PAM modules (pam_duo, pam_u2f, pam_google_authenticator)"

    local mfa_status="NOT DETECTED"
    grep -rl 'pam_google_authenticator\|pam_duo\|pam_radius\|pam_oath\|pam_u2f' /etc/pam.d/ &>/dev/null && mfa_status="DETECTED"
    echo -e "             Status: ${mfa_status}"

    e8_item "4. Restrict Admin Privileges"  "Checked: UID 0 accounts, NOPASSWD sudoers, sudo group membership"
    e8_item "5. Application Control"        "Checked: AppArmor / SELinux enforcement above"
    e8_item "6. Restrict Office Macros"     "N/A — headless Linux server"
    e8_item "7. User App Hardening"         "N/A — headless Linux server"

    e8_item "8. Regular Backups"            "Checking for backup jobs..."
    local backup_found
    backup_found=$(find /etc/cron.d /etc/cron.daily /etc/cron.weekly /var/spool/cron -type f 2>/dev/null \
        | xargs grep -l -iE 'borg|restic|rsync|bacula|amanda|duplicati|backup' 2>/dev/null | head -3 || true)
    if [ -n "$backup_found" ]; then
        echo -e "             ${GREEN}Backup jobs found:${NC} $backup_found"
    else
        echo -e "             ${YELLOW}No recognisable backup jobs found in cron — verify backup solution manually${NC}"
    fi
}

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
main() {
    echo
    echo -e "${BOLD}  tekadm Linux Security Hardening Audit${NC}"
    echo -e "  $(date '+%Y-%m-%d %H:%M:%S')  |  Host: $(hostname)  |  Kernel: $(uname -r)"
    echo -e "  Distro family: ${DISTRO_FAMILY}  |  Running as: $(id -un) (uid=$(id -u))"
    echo

    check_root
    check_ssh
    check_users
    check_filesystem
    check_sysctl
    check_firewall
    check_services
    check_updates
    check_logging
    check_mac
    check_essential_eight

    # Summary
    header "AUDIT SUMMARY"
    echo -e "  ${GREEN}PASS: ${PASS}${NC}   ${RED}FAIL: ${FAIL}${NC}   ${YELLOW}WARN: ${WARN}${NC}   ${BLUE}INFO: ${INFO_COUNT}${NC}"
    echo
    [ "$FAIL" -gt 0 ] && echo -e "  ${RED}Action required: ${FAIL} check(s) failed.${NC}"
    [ "$WARN" -gt 0 ] && echo -e "  ${YELLOW}Review recommended: ${WARN} warning(s) need manual assessment.${NC}"
    [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ] && echo -e "  ${GREEN}All checks passed.${NC}"
    [ "$(id -u)" -ne 0 ] && echo -e "  ${YELLOW}Re-run as root for complete results: sudo $0${NC}"
    echo -e "  $(printf '=%.0s' {1..56})"
    echo

    [ "$FAIL" -gt 0 ] && exit 1
    exit 0
}

main
