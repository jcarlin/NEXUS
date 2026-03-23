#!/usr/bin/env bash
# autoscale_workers.sh — Scale Celery workers based on VM CPU usage.
#
# Scales UP to MAX_WORKERS when CPU < SCALE_UP_BELOW (headroom available).
# Scales DOWN to MIN_WORKERS when CPU > SCALE_DOWN_ABOVE (overloaded).
# Does nothing when CPU is between thresholds.
#
# Usage:
#   ./scripts/autoscale_workers.sh              # one-shot check
#   ./scripts/autoscale_workers.sh --loop 60    # check every 60s
#
# Install as cron (every 2 minutes):
#   */2 * * * * cd ~/nexus && ./scripts/autoscale_workers.sh >> /var/log/autoscale.log 2>&1

set -euo pipefail

# --- Configuration -----------------------------------------------------------
MIN_WORKERS=3
MAX_WORKERS=4
SCALE_UP_BELOW=55    # scale up when CPU% < this
SCALE_DOWN_ABOVE=85  # scale down when CPU% > this
COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml"
# -----------------------------------------------------------------------------

get_cpu_usage() {
    # 1-minute load average as percentage of available CPUs
    local cores
    cores=$(nproc)
    local load
    load=$(awk '{print $1}' /proc/loadavg)
    awk -v load="$load" -v cores="$cores" 'BEGIN { printf "%.0f", (load / cores) * 100 }'
}

get_worker_count() {
    $COMPOSE ps --status running --format '{{.Name}}' 2>/dev/null | grep -c 'worker' || echo 0
}

scale_workers() {
    local target=$1
    local current
    current=$(get_worker_count)

    if [ "$current" -eq "$target" ]; then
        return 0
    fi

    echo "[$(date -Iseconds)] Scaling workers: $current -> $target"
    $COMPOSE up -d --scale "worker=$target" worker 2>&1 | tail -5
}

run_check() {
    local cpu
    cpu=$(get_cpu_usage)
    local current
    current=$(get_worker_count)

    echo "[$(date -Iseconds)] CPU=${cpu}% workers=${current} (thresholds: up<${SCALE_UP_BELOW}% down>${SCALE_DOWN_ABOVE}%)"

    if [ "$cpu" -lt "$SCALE_UP_BELOW" ] && [ "$current" -lt "$MAX_WORKERS" ]; then
        scale_workers "$MAX_WORKERS"
    elif [ "$cpu" -gt "$SCALE_DOWN_ABOVE" ] && [ "$current" -gt "$MIN_WORKERS" ]; then
        scale_workers "$MIN_WORKERS"
    fi
}

# --- Main --------------------------------------------------------------------
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--loop" ]; then
    interval="${2:-60}"
    echo "[$(date -Iseconds)] Autoscaler starting (interval=${interval}s, min=${MIN_WORKERS}, max=${MAX_WORKERS})"
    while true; do
        run_check
        sleep "$interval"
    done
else
    run_check
fi
