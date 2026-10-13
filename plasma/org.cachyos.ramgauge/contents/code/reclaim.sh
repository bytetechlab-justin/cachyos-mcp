#!/bin/sh
# Ask the kernel to reclaim this user's idle memory through cgroup v2 memory.reclaim.
# Nothing is killed or deleted and no root is needed: idle pages are compressed into
# swap/zram and unused file cache is released. Prints freed_kb=<n> or error=<reason>.
set -u
uid=$(id -u)
cgroup=${RAMGAUGE_CGROUP:-/sys/fs/cgroup/user.slice/user-$uid.slice/user@$uid.service}
meminfo=${RAMGAUGE_MEMINFO:-/proc/meminfo}

stat_kb() { awk -v key="$1" '$1 == key { print int($2 / 1024) }' "$cgroup/memory.stat"; }
available_kb() { awk '$1 == "MemAvailable:" { print $2 }' "$meminfo"; }

if [ ! -w "$cgroup/memory.reclaim" ] || [ ! -r "$cgroup/memory.stat" ]; then
    echo "error=unsupported"
    exit 1
fi
before=$(available_kb)
inactive_anon=$(stat_kb inactive_anon)
inactive_file=$(stat_kb inactive_file)
# Only the pages the kernel already considers idle, in small steps, for at most 30 seconds.
target=$(( ${inactive_anon:-0} + ${inactive_file:-0} ))
chunk=262144
deadline=$(( $(date +%s) + 30 ))
while [ "$target" -gt 0 ] && [ "$(date +%s)" -lt "$deadline" ]; do
    step=$chunk
    [ "$target" -lt "$step" ] && step=$target
    # The write fails once the kernel cannot reclaim a full step; that is the stop signal.
    echo "${step}K" 2>/dev/null > "$cgroup/memory.reclaim" || break
    target=$(( target - step ))
done
after=$(available_kb)
freed=$(( ${after:-0} - ${before:-0} ))
[ "$freed" -lt 0 ] && freed=0
echo "freed_kb=$freed"
