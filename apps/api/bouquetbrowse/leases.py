"""Short claims and fenced writes. Network work must occur between transactions."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import or_, select, update

from . import db as database
from .db import utcnow
from .models import Job
from .providers import CapabilityError

LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 30


@dataclass(frozen=True)
class Lease:
    job_id: str
    token: str


def claim(factory=None, kinds=None, exclude_kinds=None):
    factory = factory or database.SessionLocal
    with factory() as db:
        now = utcnow()
        query = select(Job).where(
            Job.cancelled_at.is_(None),
            Job.run_after <= now,
            or_(Job.state == "queued", (Job.state == "processing") & (Job.lease_until < now)),
        )
        if kinds is not None:
            query = query.where(Job.kind.in_(kinds))
        if exclude_kinds:
            query = query.where(Job.kind.not_in(exclude_kinds))
        job = db.scalar(query.order_by(Job.run_after, Job.id).with_for_update(skip_locked=True).limit(1))
        if not job:
            return None
        token = str(uuid4())
        changed = db.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.state == job.state,
                Job.attempts == job.attempts,
                Job.cancelled_at.is_(None),
            )
            .values(
                state="processing",
                attempts=job.attempts + 1,
                lease_token=token,
                lease_until=now + timedelta(seconds=LEASE_SECONDS),
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            return None
        db.commit()
        return Lease(job.id, token)


def guard(db, lease, renew=False):
    now = utcnow()
    # The conditional update both verifies ownership and locks the row until commit.
    values = {"lease_until": now + timedelta(seconds=LEASE_SECONDS)} if renew else {"lease_token": lease.token}
    result = db.execute(
        update(Job)
        .where(
            Job.id == lease.job_id,
            Job.lease_token == lease.token,
            Job.state == "processing",
            Job.cancelled_at.is_(None),
            Job.lease_until > now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise CapabilityError("Job ownership expired or was cancelled.", "lease_lost")
    return db.get(Job, lease.job_id, populate_existing=True)


def heartbeat(lease, factory=None):
    with (factory or database.SessionLocal)() as db:
        guard(db, lease, renew=True)
        db.commit()


@contextmanager
def keep_alive(lease, factory=None):
    stop, lost = Event(), Event()

    def maintain():
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                heartbeat(lease, factory)
            except Exception:
                lost.set()
                return

    thread = Thread(target=maintain, name="job-heartbeat", daemon=True)
    thread.start()
    try:
        yield lost
    finally:
        stop.set()
        thread.join(timeout=5)


def cancel(db, job_id):
    db.execute(
        update(Job)
        .where(Job.id == job_id, Job.state.in_(["queued", "processing", "failed", "paused"]))
        .values(
            state="cancelled",
            cancelled_at=utcnow(),
            lease_token=None,
            lease_until=None,
        )
    )
