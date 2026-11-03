"""Controller-owned action menus and bounded planning context. No browser I/O."""

import re
from urllib.parse import urlsplit

from pydantic import Field, create_model

from .browser import BrowserAction, search_url
from .schemas import StrictModel

PROMPT_VERSION = "discovery-menu-v2"


def choose_recent_action(snapshot, observation_id, completed):
    """Follow issued targets in Recent result order, without a provider call."""
    url = snapshot["url"]
    search = urlsplit(url).path == "/search"
    opened = {r.continuation.get("url") for r in completed if r.action == "open_post"}
    expanded = any(r.action == "expand_replies" and r.continuation.get("url") == url for r in completed)
    targets = snapshot["targets"]
    for kind in ("open_post", "scroll") if search else ("expand_replies", "back"):
        for target, data in targets.items():
            if data["kind"] != kind:
                continue
            if kind == "open_post" and (not data.get("url") or data["url"] in opened):
                continue
            if kind == "expand_replies" and expanded:
                continue
            return BrowserAction(action=kind, target=target, observation_version=observation_id)
    return BrowserAction(action="finish", observation_version=observation_id)


def action_menu(snapshot, queries):
    menu = {}
    context = snapshot.get("planning_context", {})
    visited = {r.get("url") for r in context.get("recent_actions", []) if r["state"] == "completed"}
    for target, data in list(snapshot["targets"].items())[:60]:
        if context.get("discovery_mode") == "recent_search" and data["kind"] in {
            "visit_profile",
            "open_sort",
            "set_sort",
        }:
            continue
        if data["kind"] in {"open_post", "visit_profile"} and (
            data.get("url") == snapshot["url"] or context.get("no_yield_steps", 0) and data.get("url") in visited
        ):
            continue
        menu[f"A{len(menu) + 1}"] = {"action": data["kind"], "target": target, "query": None}
    for query in queries:
        if search_url(query) != snapshot["url"] and search_url(query) not in visited:
            menu[f"A{len(menu) + 1}"] = {"action": "search", "target": None, "query": query}
    menu["FINISH"] = {"action": "finish", "target": None, "query": None}
    return menu


def selection_schema(menu):
    # Keep parsing permissive for this bounded string so a completed but invalid
    # selection is receipted before application validation (never auto-rebill it).
    # Providers receive the exact enum; the server independently checks membership.
    return create_model(
        "PlannerSelection",
        __base__=StrictModel,
        candidate_id=(str, Field(max_length=80, json_schema_extra={"enum": list(menu)})),
    )


def resolve_selection(menu, candidate_id, observation_id):
    selected = menu.get(candidate_id)
    if selected is None:
        # An invalid sentinel is rejected by the controller and enters bounded
        # recovery, even if a provider ignores the request's enum constraint.
        selected = {"action": "open_post", "target": "invalid_candidate", "query": None}
    return BrowserAction(**selected, observation_version=observation_id)


def evidence_excerpt(text, budget=1000):
    """Preserve leading context plus commercial clues later in long captions."""
    if len(text) <= budget:
        return text
    fragments = [text[:400]]
    for match in re.finditer(r"\d|giá|price|Hà Nội|Hanoi|giao|delivery", text[400:], re.IGNORECASE):
        offset = 400 + match.start()
        fragments.append(text[max(400, offset - 80) : offset + 160])
        if sum(map(len, fragments)) >= budget:
            break
    return " […] ".join(fragments)[:budget]
