#!/usr/bin/env bash
# Syncs wine-tracker/ into wine-tracker-dev/ and patches the add-on config
# so Home Assistant lists a parallel "Wine Tracker (Dev)" add-on built from
# the current main branch. Usage: scripts/sync-dev-addon.sh <suffix>
# Example: scripts/sync-dev-addon.sh dev.2  ->  version "1.11.0-dev.2"
set -euo pipefail
cd "$(dirname "$0")/.."

SUFFIX="${1:?usage: sync-dev-addon.sh <suffix>, e.g. dev.1}"

rsync -a --delete \
  --exclude 'app/data/' \
  --exclude 'app/__pycache__/' \
  --exclude 'tests/__pycache__/' \
  --exclude '.pytest_cache/' \
  wine-tracker/ wine-tracker-dev/

python3 - "$SUFFIX" <<'EOF'
import re
import sys

suffix = sys.argv[1]
path = "wine-tracker-dev/config.yaml"
with open(path) as f:
    cfg = f.read()

cfg = re.sub(r'^name: .*$', 'name: "WeinSommelier (Dev)"', cfg, count=1, flags=re.M)
cfg = re.sub(r'^description: .*$',
             'description: "Development build of WeinSommelier - unstable, for testing"',
             cfg, count=1, flags=re.M)
cfg = re.sub(r'^version: "([^"]+)"$',
             lambda m: f'version: "{m.group(1)}-{suffix}"', cfg, count=1, flags=re.M)
cfg = re.sub(r'^slug: .*$', 'slug: "weinsommelier_dev"', cfg, count=1, flags=re.M)
cfg = cfg.replace("ports:\n  5050/tcp: 5052", "ports:\n  5050/tcp: 5053", 1)
cfg = re.sub(r'^panel_title: .*$', 'panel_title: "WeinSommelier Dev"', cfg, count=1, flags=re.M)
cfg = cfg.replace("DATA_DIR: /share/weinsommelier\n",
                  "DATA_DIR: /share/weinsommelier-dev\n", 1)

with open(path, "w") as f:
    f.write(cfg)

version = re.search(r'^version: "([^"]+)"$', cfg, flags=re.M).group(1)
print(f"wine-tracker-dev synced, version {version}")
EOF
