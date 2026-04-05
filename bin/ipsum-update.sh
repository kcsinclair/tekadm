#!/usr/bin/env bash

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

if [ -f "bin/ipsum-update.sh" ]; then
    echo this is the project root, proceeding with update
else
    echo "ipsum-update.sh not found. Please run this script from the project root."
    exit 1
fi

if [ -d "ipsum" ]; then
    cd ipsum
else
    mkdir ipsum
    cd ipsum
fi

curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/1.txt -o ipsum-level1.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/2.txt -o ipsum-level2.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/3.txt -o ipsum-level3.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/4.txt -o ipsum-level4.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/5.txt -o ipsum-level5.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/6.txt -o ipsum-level6.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/7.txt -o ipsum-level7.txt
curl https://raw.githubusercontent.com/stamparm/ipsum/refs/heads/master/levels/8.txt -o ipsum-level8.txt

# everything 3 and above is bad
curl -fsSL https://raw.githubusercontent.com/stamparm/ipsum/master/ipsum.txt 2>/dev/null | grep -v "^#" | grep -Ev '[[:space:]]([12])$' | cut -f 1 > ipsum-bad.txt

