#!/usr/bin/env bash
# Source this file to add tekadm/bin to your PATH
# Usage: source /path/to/tekadm/init.sh

TEKADM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$TEKADM_DIR/bin:$PATH"
