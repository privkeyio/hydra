"""Celery application configuration for distributed task processing."""

import os

from celery import Celery
from kombu import Exchange, Queue

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_url = os.getenv("BROKER_URL", redis_url)
result_backend = os.getenv("RESULT_BACKEND", redis_url)

app = Celery("hydra", broker=broker_url, backend=result_backend)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=3,
    result_expires=3600,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

default_exchange = Exchange("default", type="direct")
priority_exchange = Exchange("priority", type="direct")

app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default", priority=1),
    Queue("high_priority", priority_exchange, routing_key="high", priority=10),
    Queue("dead_letter", default_exchange, routing_key="dead_letter", priority=0),
)

app.conf.task_routes = {
    "hydra.workers.tasks.generate_code": {"queue": "default"},
    "hydra.workers.tasks.execute_workflow": {"queue": "default"},
    "hydra.workers.tasks.generate_code_priority": {"queue": "high_priority"},
    "hydra.workers.tasks.execute_workflow_priority": {"queue": "high_priority"},
}

app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

if __name__ == "__main__":
    app.start()
