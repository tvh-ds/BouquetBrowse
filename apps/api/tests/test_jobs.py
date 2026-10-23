from datetime import timedelta

from bouquetbrowse.db import utcnow
from bouquetbrowse.models import Job
from bouquetbrowse.pipeline import enqueue
from bouquetbrowse.worker import claim_job, run_once


def test_job_enqueue_idempotent(db):
    first = enqueue(db, "retention", {}, "once")
    second = enqueue(db, "retention", {}, "once")
    assert first.id == second.id


def test_expired_lease_is_reclaimed(db):
    job = Job(
        kind="retention",
        payload={},
        idempotency_key="expired",
        state="processing",
        attempts=1,
        lease_until=utcnow() - timedelta(minutes=1),
    )
    db.add(job)
    db.commit()
    assert claim_job() == job.id
    db.expire_all()
    assert db.get(Job, job.id).attempts == 2


def test_unsupported_job_is_visible_failure(db):
    job = enqueue(db, "unknown-stage", {}, "unknown")
    db.commit()
    assert run_once()
    db.expire_all()
    assert db.get(Job, job.id).state == "failed"


def test_retry_does_not_process_future_job(db):
    job = Job(kind="retention", payload={}, idempotency_key="future", run_after=utcnow() + timedelta(hours=1))
    db.add(job)
    db.commit()
    assert claim_job() is None
