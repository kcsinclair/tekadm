#!/bin/env bash

# simple effective works.
for file in /proc/*/status ; do awk '/VmSwap|Name/{printf $2 " " $3}END{ print ""}' $file; done | grep kB | sort -k 2 -n
echo
grep -E "SwapTotal|SwapFree" /proc/meminfo

