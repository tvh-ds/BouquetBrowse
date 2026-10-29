from datetime import timedelta

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from bouquetbrowse import db as database
from bouquetbrowse import model_calls, worker
from bouquetbrowse.config import Settings
from bouquetbrowse.db import aware, utcnow
from bouquetbrowse.graphs import discovery_graph, invoke_graph, offer_graph
from bouquetbrowse.leases import cancel, claim, guard, heartbeat
from bouquetbrowse.model_calls import CallScope, authorize_replay, call_scope, invoke_once
from bouquetbrowse.models import CostEntry, Job
from bouquetbrowse.pipeline import enqueue
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.runtime_models import ModelCall


def test_reclaimed_job_fences_old_owner_and_heartbeat_renews(db):
    job = enqueue(db, "retention", {}, "fenced")
    db.commit()
    first = claim()
    db.expire_all()
    job.lease_until = utcnow() - timedelta(seconds=1)
    db.commit()
    second = claim()
    assert second.token != first.token
    with pytest.raises(CapabilityError, match="ownership"):
        heartbeat(first)
    heartbeat(second)
    db.expire_all()
    assert aware(db.get(Job, job.id).lease_until) > utcnow() + timedelta(seconds=110)


def test_cancellation_during_external_work_prevents_result_commit(db, monkeypatch):
    job = enqueue(db, "retention", {}, "cancel-during-call")
    db.commit()

    def external(*_):
        # No claim/read transaction is held while external work executes.
        with database.SessionLocal() as separate:
            cancel(separate, job.id)
            separate.commit()

    monkeypatch.setattr(worker, "prepare_external", external)
    assert worker.run_once()
    db.expire_all()
    assert db.get(Job, job.id).state == "cancelled"
    assert db.get(Job, job.id).result is None


def test_cancelled_and_other_role_jobs_are_not_claimed(db):
    cancelled = enqueue(db, "retention", {}, "cancelled")
    enqueue(db, "offer-graph", {}, "offer")
    db.commit()
    cancel(db, cancelled.id)
    db.commit()
    assert claim(kinds=["retention"]) is None
    assert claim(kinds=["offer-graph"])


def test_enqueue_rejects_reused_key_for_different_work(db):
    enqueue(db, "retention", {}, "same-key")
    with pytest.raises(ValueError, match="different work"):
        enqueue(db, "sync", {"source": "threads"}, "same-key")


def test_receipt_reuses_result_without_second_paid_call(db):
    calls = []

    def paid():
        calls.append(True)
        return {"value": "fictional result"}, {"input_tokens": 12}, 0.003

    first = invoke_once("fictional-model", {"input": "test"}, paid)
    assert invoke_once("fictional-model", {"input": "test"}, paid) == first
    assert len(calls) == 1
    assert db.scalar(select(func.count()).select_from(ModelCall)) == 1
    assert db.scalar(select(CostEntry)).amount_microusd == 3000


def test_uncertain_paid_call_never_automatically_replays(db):
    calls = []

    def timed_out():
        calls.append(True)
        raise TimeoutError("fictional timeout after dispatch")

    for _ in range(2):
        with pytest.raises(CapabilityError):
            invoke_once("fictional-model", {"input": "timeout"}, timed_out)
    assert len(calls) == 1
    assert db.scalar(select(ModelCall)).state == "uncertain"
    assert db.scalar(select(CostEntry)).amount_microusd == 100000
    assert db.scalar(select(CostEntry)).state == "uncertain"


def test_explicit_replay_preserves_old_reservation_and_records_actor(db):
    with call_scope(CallScope("explicit-replay-test", 300000)):
        with pytest.raises(CapabilityError):
            invoke_once("fictional-model", {}, lambda: (_ for _ in ()).throw(TimeoutError()))
        call = db.scalar(select(ModelCall))
        authorize_replay(db, call.id, "fictional-admin")
        db.commit()
        result, _ = invoke_once("fictional-model", {}, lambda: ({"ok": True}, {}, 0.001))
    assert result == {"ok": True}
    assert db.scalar(select(func.count()).select_from(ModelCall)) == 2
    assert db.get(ModelCall, call.id).replay_actor == "fictional-admin"
    assert sum(db.scalars(select(CostEntry.amount_microusd))) == 101000


def test_uncertain_reservations_count_toward_budget(db, monkeypatch):
    monkeypatch.setattr(model_calls, "get_settings", lambda: Settings(monthly_model_budget_usd=0.01, _env_file=None))
    with pytest.raises(CapabilityError):
        invoke_once("fictional", {"one": 1}, lambda: (_ for _ in ()).throw(TimeoutError()), 0.006)
    with pytest.raises(CapabilityError, match="budget reached"):
        invoke_once("fictional", {"two": 2}, lambda: ({}, {}, 0), 0.006)


class DiscoveryServices:
    def __init__(self):
        self.calls = []
        self.fail_once = True

    def stage(self, name, state):
        self.calls.append(name)
        if name == "observe" and self.fail_once:
            self.fail_once = False
            raise RuntimeError("fictional crash")
        if name == "dispatch":
            return {"action_count": 1, "stop": True}
        return {}


def test_graph_resumes_after_checkpoint_without_repeating_prior_nodes():
    services = DiscoveryServices()
    graph = discovery_graph(services, InMemorySaver())
    with pytest.raises(RuntimeError):
        invoke_graph(graph, "fictional-execution")
    result = invoke_graph(graph, "fictional-execution")
    assert result["action_count"] == 1
    assert services.calls.count("load_limits") == 1
    assert services.calls.count("select_task") == 1
    assert services.calls.count("observe") == 2
    assert services.calls[-1] == "finish"


def test_graph_state_rejects_source_text_and_objects():
    class InvalidServices:
        def stage(self, name, state):
            return {"caption": "Buyer text must stay in evidence tables"}

    with pytest.raises(ValueError, match="compact"):
        invoke_graph(discovery_graph(InvalidServices(), InMemorySaver()), "invalid-state")


def test_offer_graph_rechecks_once_then_commits():
    class Services:
        def __init__(self):
            self.calls = []

        def stage(self, name, state):
            self.calls.append(name)
            return {"needs_recheck": True} if name == "recognize" else {}

    services = Services()
    invoke_graph(offer_graph(services, InMemorySaver()), "offer-execution")
    assert services.calls.count("recheck") == 1
    assert services.calls[-1] == "commit"


def test_stale_worker_cannot_renew_or_publish(db):
    enqueue(db, "retention", {}, "stale")
    db.commit()
    lease = claim()
    cancel(db, lease.job_id)
    db.commit()
    with pytest.raises(CapabilityError):
        guard(db, lease)


def test_execution_creation_pins_inputs_and_rejects_key_reassignment(db):
    from bouquetbrowse.executions import create_execution, pinned_execution

    first = create_execution(db, "discovery", "fictional-run", {"prompt_version": "one"}, "input")
    assert create_execution(db, "discovery", "fictional-run", {"prompt_version": "one"}, "input").id == first.id
    with pytest.raises(ValueError, match="different inputs"):
        create_execution(db, "discovery", "fictional-run", {"prompt_version": "two"}, "input")
    first.behavior_version = "incompatible-future-graph"
    with pytest.raises(ValueError, match="compatible"):
        pinned_execution(db, first.id)
    with pytest.raises(ValueError, match="credentials"):
        create_execution(db, "discovery", "bad-config", {"api_key": "fictional"}, "input")


def test_postgres_checkpoints_survive_new_connections(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL checkpointer integration runs in the PG suite")
    from uuid import uuid4

    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    from bouquetbrowse.graphs import postgres_checkpointer

    url = db.bind.url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as owner:
        owner.execute("CREATE SCHEMA IF NOT EXISTS graph_checkpoints")
        owner.execute("SET search_path TO graph_checkpoints")
        PostgresSaver(owner).setup()
    services = DiscoveryServices()
    execution_id = str(uuid4())
    with postgres_checkpointer(url) as saver:
        with pytest.raises(RuntimeError):
            invoke_graph(discovery_graph(services, saver), execution_id)
    with postgres_checkpointer(url) as saver:
        assert invoke_graph(discovery_graph(services, saver), execution_id)["action_count"] == 1
        saver.delete_thread(execution_id)
    assert services.calls.count("load_limits") == 1


def test_postgres_concurrent_reservations_cannot_overbook(db, monkeypatch):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Concurrent budget locking is a PostgreSQL contract")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    monkeypatch.setattr(model_calls, "get_settings", lambda: Settings(monthly_model_budget_usd=0.01, _env_file=None))
    ready = Barrier(2)

    def reserve(index):
        ready.wait(timeout=10)
        try:
            invoke_once("fictional", {"concurrent": index}, lambda: ({"ok": True}, {}, 0.006), 0.006)
            return "ok"
        except CapabilityError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(reserve, [1, 2])) == ["budget_exhausted", "ok"]
    assert sum(db.scalars(select(CostEntry.amount_microusd))) == 6000
