#!/usr/bin/env python3
"""Push RabbitMQ queue depths to Cloud Monitoring for MIG autoscaling.

Polls RabbitMQ management API every 30s and writes per-queue depth as
custom metrics. The MIG autoscaler reads these to scale satellite workers.

Run as a systemd service on the main VM (not in Docker — needs gcloud auth).

Requirements: pip install google-cloud-monitoring requests
"""

import os
import sys
import time

import requests
from google.cloud import monitoring_v3

PROJECT = os.environ.get("GCP_PROJECT", "vault-ai-487703")
RMQ_HOST = os.environ.get("RMQ_HOST", "localhost")
RMQ_PORT = os.environ.get("RMQ_PORT", "15672")
RMQ_VHOST = os.environ.get("RMQ_VHOST", "nexus")
RMQ_USER = os.environ.get("RMQ_USER", "nexus")
RMQ_PASS = os.environ.get("RMQ_PASS", "nexus")
INTERVAL = int(os.environ.get("METRIC_INTERVAL", "30"))

TRACKED_QUEUES = {"bulk", "default", "ner", "background"}

RMQ_URL = f"http://{RMQ_HOST}:{RMQ_PORT}/api/queues/{RMQ_VHOST}"

client = monitoring_v3.MetricServiceClient()
project_name = f"projects/{PROJECT}"


def push_metric(queue_name: str, depth: int) -> None:
    series = monitoring_v3.TimeSeries()
    series.metric.type = f"custom.googleapis.com/rabbitmq/queue_depth/{queue_name}"
    series.resource.type = "global"

    now = time.time()
    interval = monitoring_v3.TimeInterval()
    interval.end_time.seconds = int(now)
    interval.end_time.nanos = int((now % 1) * 1e9)

    point = monitoring_v3.Point()
    point.interval = interval
    point.value.int64_value = depth
    series.points = [point]

    client.create_time_series(request={"name": project_name, "time_series": [series]})


def collect_and_push() -> None:
    try:
        resp = requests.get(RMQ_URL, auth=(RMQ_USER, RMQ_PASS), timeout=10)
        resp.raise_for_status()
        queues = resp.json()
    except Exception as e:
        print(f"[WARN] Failed to fetch RabbitMQ queues: {e}", file=sys.stderr)
        return

    for q in queues:
        name = q.get("name", "")
        if name in TRACKED_QUEUES:
            depth = q.get("messages_ready", 0)
            try:
                push_metric(name, depth)
                print(f"[OK] {name}: {depth} messages")
            except Exception as e:
                print(f"[WARN] Failed to push metric for {name}: {e}", file=sys.stderr)


def main() -> None:
    print(f"Queue metric exporter starting (project={PROJECT}, interval={INTERVAL}s)")
    print(f"RabbitMQ: {RMQ_URL}")
    print(f"Tracked queues: {sorted(TRACKED_QUEUES)}")

    while True:
        collect_and_push()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
