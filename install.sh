#!/usr/bin/env bash
# Install tekadm: fix bin/ permissions and add sourcing to shell rc file

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

set -euo pipefail

TEKADM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$TEKADM_DIR/bin"
SOURCE_LINE="source $TEKADM_DIR/init.sh"

# --- Fix permissions on shell scripts in bin/ ---
echo "Checking permissions on scripts in $BIN_DIR ..."
for script in "$BIN_DIR"/*.sh; do
    [ -f "$script" ] || continue
    if [ ! -x "$script" ]; then
        chmod +x "$script"
        echo "  Fixed: $(basename "$script") (added execute permission)"
    else
        echo "  OK:    $(basename "$script")"
    fi
done

# --- Determine shell rc file ---
RC_FILE=""
case "$(basename "$SHELL")" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    *)
        echo "Unsupported shell: $SHELL"
        echo "Manually add the following to your shell rc file:"
        echo "  $SOURCE_LINE"
        exit 1
        ;;
esac

# --- Add source line if not already present ---
if grep -qF "source $TEKADM_DIR/init.sh" "$RC_FILE" 2>/dev/null; then
    echo "Already installed in $RC_FILE"
else
    echo "" >> "$RC_FILE"
    echo "# tekadm" >> "$RC_FILE"
    echo "$SOURCE_LINE" >> "$RC_FILE"
    echo "Added to $RC_FILE"
fi

echo "Done. Run 'source $RC_FILE' or open a new terminal to activate."
