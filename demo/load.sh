#!/usr/bin/env bash
set -e
here="$(cd "$(dirname "$0")" && pwd)"
target="$here/../reports"
mkdir -p "$target/research" "$target/campaigns"
cp -r "$here/data/research/." "$target/research/"
cp -r "$here/data/campaigns/." "$target/campaigns/"
echo "Demo data copied to $target"
