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
tenant_exchange = Exchange("tenant", type="topic")

app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default", priority=1),
    Queue("high_priority", priority_exchange, routing_key="high", priority=10),
    Queue("dead_letter", default_exchange, routing_key="dead_letter", priority=0),
)

def get_tenant_queue_name(tenant_id: str, priority: bool = False) -> str:
    """Get queue name for tenant."""
    suffix = "_priority" if priority else ""
    return f"tenant_{tenant_id}{suffix}"

def register_tenant_queue(tenant_id: str, priority: bool = False):
    """Dynamically register a tenant-specific queue."""
    queue_name = get_tenant_queue_name(tenant_id, priority)
    routing_key = f"tenant.{tenant_id}.{'high' if priority else 'normal'}"
    queue_priority = 10 if priority else 5

    queue = Queue(
        queue_name,
        tenant_exchange,
        routing_key=routing_key,
        priority=queue_priority,
        queue_arguments={
            'x-max-priority': 10,
            'x-message-ttl': 3600000  # 1 hour TTL
        }
    )

    # Add queue to configuration
    existing_queues = list(app.conf.task_queues)
    existing_queues.append(queue)
    app.conf.task_queues = tuple(existing_queues)

    return queue_name

app.conf.task_routes = {
    "hydra.workers.tasks.generate_code": {"queue": "default"},
    "hydra.workers.tasks.execute_workflow": {"queue": "default"},
    "hydra.workers.tasks.generate_code_priority": {"queue": "high_priority"},
    "hydra.workers.tasks.execute_workflow_priority": {"queue": "high_priority"},
    "hydra.workers.tasks.generate_code_tenant": {"exchange": "tenant", "routing_key": "tenant.*"},
    "hydra.workers.tasks.execute_workflow_tenant": {"exchange": "tenant", "routing_key": "tenant.*"},
}

app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

if __name__ == "__main__":
    app.start()
