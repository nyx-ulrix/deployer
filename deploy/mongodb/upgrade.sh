#!/bin/bash
# Deployer MongoDB upgrade step (docs/BACKUPS.md "MongoDB versions", audit A-143).
#
# MongoDB only opens data whose featureCompatibilityVersion (FCV) is its own major or the one before,
# so data is upgraded one major at a time. Run in a mongo:<N> container (compose services
# `mongodb-upgrade-<N>`, no network) with the stopped managed MongoDB's volume at /data/db, this lifts
# the data from FCV N-1 to N: mongod starts standalone on 127.0.0.1, setFeatureCompatibilityVersion
# runs, mongod shuts down cleanly. installer/lib/common.ps1 Update-DeployerMongo runs the steps.
#
# The FCV is recorded in /data/db/deployer-fcv (written by deploy/mongodb/entrypoint.sh for a new
# volume and here after each step). Data without it is from MongoDB 5.0, the only version before A-143.
# Exit codes: 0 upgraded or nothing to do, 3 the data needs an earlier step first, other = failure.
set -euo pipefail

db=/data/db
marker="$db/deployer-fcv"
target="$(mongod --version | sed -n 's/^db version v\([0-9]*\)\..*/\1.0/p')"
if [ -z "$target" ]; then
    echo "deployer: could not read the mongod version" >&2
    exit 1
fi
if [ ! -e "$db/WiredTiger" ]; then
    echo "deployer: no MongoDB data yet; nothing to upgrade"
    exit 0
fi
current="$(tr -d '\r\n' < "$marker" 2>/dev/null || true)"
current="${current:-5.0}"
if [ "${current%%.*}" -ge "${target%%.*}" ]; then
    echo "deployer: MongoDB data is already at $current"
    exit 0
fi
if [ "${current%%.*}" -ne "$(( ${target%%.*} - 1 ))" ]; then
    echo "deployer: MongoDB data is at $current; MongoDB $target needs $(( ${target%%.*} - 1 )).0 first"
    exit 3
fi

echo "deployer: upgrading MongoDB data $current -> $target"
log=/tmp/deployer-mongod-upgrade.log
if ! gosu mongodb mongod --dbpath "$db" --bind_ip 127.0.0.1 --port 27017 --wiredTigerCacheSizeGB 0.25 \
        --fork --logpath "$log"; then
    tail -n 40 "$log" >&2 || true
    exit 1
fi
# setFeatureCompatibilityVersion needs `confirm: true` from 7.0 on (6.0 rejects the field).
mongosh --quiet --norc --port 27017 --eval "
    const cmd = { setFeatureCompatibilityVersion: '$target' };
    if (${target%%.*} >= 7) cmd.confirm = true;
    db.adminCommand(cmd);
    const fcv = db.adminCommand({ getParameter: 1, featureCompatibilityVersion: 1 }).featureCompatibilityVersion.version;
    if (fcv !== '$target') throw new Error('featureCompatibilityVersion is ' + fcv);
" || { gosu mongodb mongod --dbpath "$db" --shutdown || true; exit 1; }
gosu mongodb mongod --dbpath "$db" --shutdown
printf '%s\n' "$target" > "$marker"
chown mongodb:mongodb "$marker"
echo "deployer: MongoDB data is now at $target"
