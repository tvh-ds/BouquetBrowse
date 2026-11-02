from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from bouquetbrowse import discovery
from bouquetbrowse.browser import BrowserAction
from bouquetbrowse.config import Settings
from bouquetbrowse.conversation_contracts import CaptureEnvelope, MessageObservation
from bouquetbrowse.db import aware, utcnow
from bouquetbrowse.discovery import DiscoveryServices, seed_frontier, settings_row
from bouquetbrowse.executions import create_execution
from bouquetbrowse.graphs import discovery_graph, invoke_graph
from bouquetbrowse.leases import claim
from bouquetbrowse.model_calls import CallScope, call_scope
from bouquetbrowse.planner import action_menu, evidence_excerpt, resolve_selection, selection_schema
from bouquetbrowse.providers import CapabilityError
from bouquetbrowse.runtime_models import ActionReceipt, DiscoveryFrontier, ExecutionEvent, GraphExecution, ModelCall


def test_menu_resolves_only_server_owned_actions():
    snapshot = {"url": "https://www.threads.com/", "targets": {"issued": {"kind": "visit_profile"}}}
    menu = action_menu(snapshot, ["bó hoa Hà Nội"])
    assert resolve_selection(menu, "A1", "obs").model_dump() == {
        "action": "visit_profile",
        "target": "issued",
        "query": None,
        "observation_version": "obs",
    }
    assert selection_schema(menu).model_json_schema()["properties"]["candidate_id"]["enum"] == list(menu)
    assert resolve_selection(menu, "invented", "obs").target == "invalid_candidate"
    assert evidence_excerpt("x" * 900 + " giá 650k Hà Nội").endswith("650k Hà Nội")


def test_menu_avoids_known_navigation_loops():
    url = "https://www.threads.com/@fictional/post/offer"
    snapshot = {
        "url": url,
        "targets": {
            "same": {"kind": "open_post", "url": url},
            "visited": {"kind": "visit_profile", "url": "https://www.threads.com/@fictional"},
        },
        "planning_context": {
            "no_yield_steps": 1,
            "recent_actions": [{"state": "completed", "url": "https://www.threads.com/@fictional"}],
        },
    }
    assert action_menu(snapshot, []) == {"FINISH": {"action": "finish", "target": None, "query": None}}


def test_live_transport_serializes_candidate_enum_without_live_network(db, monkeypatch):
    from test_groq_provider import fake_provider, groq_settings

    requests = fake_provider(monkeypatch, parsed={"candidate_id": "FINISH"})
    settings = groq_settings()
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)
    observation = SimpleNamespace(id="obs", snapshot={"url": "https://www.threads.com/", "targets": {}})
    with call_scope(CallScope("fictional-groq-run", 350000)):
        assert discovery.choose_action(settings.active_planner_model, observation, []).action == "finish"
    schema = requests[0][1]["response_format"]["json_schema"]["schema"]
    assert "FINISH" in schema["properties"]["candidate_id"]["enum"]


def test_planner_receipts_distinguish_corrective_observations(db, monkeypatch):
    settings = Settings(openai_api_key="fictional", _env_file=None)
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)
    requests = []

    def respond(settings, **kwargs):
        requests.append(kwargs)
        return SimpleNamespace(
            output_parsed=kwargs["text_format"](candidate_id="invented"),
            usage=None,
            model=settings.active_planner_model,
        )

    monkeypatch.setattr(discovery, "structured_response", respond)
    for identity, feedback in [("obs-one", None), ("obs-two", "invalid_action_target")]:
        observation = SimpleNamespace(
            id=identity,
            snapshot={"url": "https://www.threads.com/", "targets": {}, "planning_context": {"correction": feedback}},
        )
        with call_scope(CallScope("fictional-run", 350000)):
            assert discovery.choose_action(settings.active_planner_model, observation, []).target == "invalid_candidate"
    assert len(requests) == 2
    assert all(c.state == "succeeded" for c in db.scalars(select(ModelCall)))
    assert "invalid_action_target" in str(requests[1]["input"])


def test_new_observation_cannot_replay_uncertain_identical_evidence(db, monkeypatch):
    settings = Settings(openai_api_key="fictional", _env_file=None)
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)
    calls = []

    def timeout(*args, **kwargs):
        calls.append(True)
        raise TimeoutError("Fictional uncertain dispatch")

    monkeypatch.setattr(discovery, "structured_response", timeout)
    for i in range(2):
        observation = SimpleNamespace(
            id=f"obs-{i}",
            snapshot={"url": "https://www.threads.com/", "targets": {}, "planning_context": {"deadline": str(i)}},
        )
        with call_scope(CallScope(f"fictional-run-{i}", 350000)):
            with pytest.raises(CapabilityError):
                discovery.choose_action(settings.active_planner_model, observation, [])
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["invalid_action_target", "stale_observation", "browser_auth_required"])
@pytest.mark.parametrize("persistent", [False, True])
def test_recovery_is_bounded_and_receipted(db, monkeypatch, failure, persistent):
    settings = Settings(discovery_enabled=True, _env_file=None)
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)
    settings_row(db).paused = False
    execution = create_execution(db, "discovery", "fictional-recovery", {"planner_model": "fictional"}, "input")
    seed_frontier(db)
    selected = db.scalar(select(DiscoveryFrontier.id).where(DiscoveryFrontier.kind == "search").limit(1))
    for task in db.scalars(select(DiscoveryFrontier)):
        if task.id != selected:
            task.due_at = utcnow() + timedelta(days=1)
    db.commit()
    lease = claim(kinds=["discovery-graph"])

    class Controller:
        navigated = False
        attempts = 0
        executed = 0

        def navigate(self, url):
            self.navigated = True

        def observe(self, flower_only=False):
            return {
                "observation_version": str(uuid4()),
                "signature": "fictional",
                "url": "https://www.threads.com/search",
                "posts": [
                    MessageObservation(
                        platform_id="offer",
                        username="fictional",
                        text="Bó hoa Hà Nội",
                        url="https://www.threads.com/@fictional/post/offer",
                    ).model_dump(mode="json")
                ],
                "targets": {},
                "sorting": "unknown",
                "profile": None,
                "remaining_expansions": 0,
            }

        def evidence_capture(self, view):
            return CaptureEnvelope(source_url=view["url"], messages=view["posts"], stop_reason="partial")

        def visual_context(self):
            return None

        def execute(self, action):
            self.attempts += 1
            if self.attempts == 1 or persistent:
                raise CapabilityError("Fictional rejected action", failure)
            self.executed += 1

    controller = Controller()
    contexts = []

    def planner(model, observation, messages, image):
        contexts.append(observation.snapshot["planning_context"])
        assert messages[0]["role"] == "unresolved"
        return BrowserAction(action="finish", observation_version=observation.id)

    saver = InMemorySaver()
    services = DiscoveryServices(execution.id, lease, controller, planner)
    if failure == "browser_auth_required":
        with pytest.raises(CapabilityError) as error:
            invoke_graph(discovery_graph(services, saver), execution.id)
        assert error.value.code == "browser_auth_required"
        assert controller.attempts == 1 and controller.executed == 0
        assert len(contexts) == 1
        return
    stage = services.stage

    def crash_after_commit(name, state):
        result = stage(name, state)
        if name == "execute":
            raise RuntimeError("Fictional crash after domain commit, before checkpoint")
        return result

    services.stage = crash_after_commit
    with pytest.raises(RuntimeError, match="Fictional crash"):
        invoke_graph(discovery_graph(services, saver), execution.id)
    # A new service object has no in-memory action; persisted receipts must win.
    graph = discovery_graph(DiscoveryServices(execution.id, lease, controller, planner), saver)
    invoke_graph(graph, execution.id)
    db.expire_all()
    receipts = db.scalars(select(ActionReceipt).order_by(ActionReceipt.created_at, ActionReceipt.id)).all()
    assert len(receipts) == 2
    assert receipts[0].state == ("skipped" if failure == "stale_observation" else "rejected")
    assert receipts[0].continuation["error_code"] == failure
    assert contexts[1]["correction"] == failure
    assert controller.executed == (0 if persistent else 1)
    assert db.get(GraphExecution, execution.id).progress["actions"] == controller.executed
    if persistent:
        assert db.scalar(select(ExecutionEvent).where(ExecutionEvent.kind == "task_deferred"))
        assert aware(db.get(DiscoveryFrontier, selected).due_at) > utcnow()
    else:
        assert receipts[1].state == "completed"
    # Completed checkpoints do not repeat browser side effects on resume.
    invoke_graph(graph, execution.id)
    assert controller.attempts == 2
