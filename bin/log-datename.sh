#!/usr/bin/env bash
#
# log-datename.sh — Rename log files by appending the date from their first line
#
# Usage: log-datename.sh <logfile> [logfile ...]
#
# Example:
#   log-datename.sh tek-access.log
#   # tek-access.log -> tek-access--2026-04-14.log
#
#   log-datename.sh *.log
#   # Renames all .log files in the current directory
#
# The date is extracted from the first Apache/Nginx timestamp found in the file:
#   [14/Apr/2026:00:05:22 +0000] -> 2026-04-14
#
# Copyright (c) 2026 Keith Sinclair — MIT License

set -euo pipefail

# Month name to number lookup
month_to_num() {
    case "$1" in
        Jan) echo "01" ;; Feb) echo "02" ;; Mar) echo "03" ;; Apr) echo "04" ;;
        May) echo "05" ;; Jun) echo "06" ;; Jul) echo "07" ;; Aug) echo "08" ;;
        Sep) echo "09" ;; Oct) echo "10" ;; Nov) echo "11" ;; Dec) echo "12" ;;
        *) echo "" ;;
    esac
}

if [ $# -eq 0 ]; then
    echo "Usage: $(basename "$0") <logfile> [logfile ...]"
    echo "Renames log files by appending the date from their first log line."
    echo ""
    echo "Example: $(basename "$0") tek-access.log"
    echo "         tek-access.log -> tek-access--2026-04-14.log"
    exit 1
fi

for file in "$@"; do
    if [ ! -f "$file" ]; then
        echo "SKIP  $file (not a file)"
        continue
    fi

    # Skip files that already have a date stamp (--YYYY-MM-DD)
    if [[ "$(basename "$file")" =~ --[0-9]{4}-[0-9]{2}-[0-9]{2} ]]; then
        echo "SKIP  $file (already has date stamp)"
        continue
    fi

    # Extract first timestamp: [14/Apr/2026:00:05:22 +0000]
    timestamp=$(head -20 "$file" | grep -o '\[[0-9]\{2\}/[A-Z][a-z]\{2\}/[0-9]\{4\}' | head -1 || true)

    if [ -z "$timestamp" ]; then
        echo "SKIP  $file (no timestamp found)"
        continue
    fi

    # Parse: [14/Apr/2026 -> day=14 mon=Apr year=2026
    day=$(echo "$timestamp" | cut -c2-3)
    mon=$(echo "$timestamp" | cut -c5-7)
    year=$(echo "$timestamp" | cut -c9-12)
    mon_num=$(month_to_num "$mon")

    if [ -z "$mon_num" ]; then
        echo "SKIP  $file (unrecognised month: $mon)"
        continue
    fi

    date_str="${year}-${mon_num}-${day}"

    # Build new filename: strip .log, append --date.log
    dir=$(dirname "$file")
    base=$(basename "$file")

    if [[ "$base" == *.log ]]; then
        newbase="${base%.log}--${date_str}.log"
    elif [[ "$base" == *.log.* ]]; then
        # Handle rotated logs like access.log.1
        stem="${base%%.*}"
        ext="${base#*.}"
        newbase="${stem}--${date_str}.${ext}"
    else
        # No .log extension — just append
        newbase="${base}--${date_str}"
    fi

    newfile="${dir}/${newbase}"

    if [ "$file" = "$newfile" ]; then
        echo "SKIP  $file (already renamed)"
        continue
    fi

    if [ -e "$newfile" ]; then
        echo "SKIP  $file -> $newbase (target already exists)"
        continue
    fi

    mv "$file" "$newfile"
    echo "OK    $file -> $newbase"
done
