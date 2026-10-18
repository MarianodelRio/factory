import json
import os
import re
import time
from pathlib import Path

from swfactory import activity

WORKSPACE = Path("/work/repo-CHG-0012-01")


def write(path: Path, content) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def hook(name, received, **payload):
    return json.dumps({"source": "claude", "worktreeId": f"r::{WORKSPACE}", "receivedAt": received,
                       "payload": {"hook_event_name": name, "cwd": str(WORKSPACE), **payload}})


def hooks_home(tmp_path):
    folder = tmp_path / ".config/orca/agent-hooks"
    write(folder / "last-status.json", {"entries": {"tab-1:leaf-live": {
        "source": "codex", "receivedAt": 1_700_000_000_000,
        "payload": {"state": "working", "prompt": "fix it, token ghp_" + "a" * 36}}}})
    write(folder / "spool/pane-leaf-old.jsonl", "\n".join([
        "",
        hook("SessionStart", 1_700_000_000_000),
        hook("UserPromptSubmit", 1_700_000_001_000, prompt="/factory-implement CHG-0012-01"),
        hook("SubagentStart", 1_700_000_002_000, agent_id="a1", agent_type="Explore"),
        hook("SubagentStop", 1_700_000_003_000, agent_id="a1", agent_type="Explore", last_assistant_message="pass",
             background_tasks=[{"id": "a1", "description": "Quality review"}]),
        hook("SubagentStop", 1_700_000_003_500, agent_id="internal", agent_type=""),
        "{not json",
        hook("Stop", 1_700_000_004_000),
    ]))
    return tmp_path


def test_hooks_give_each_pane_its_agent_and_the_typed_subagents(tmp_path):
    hooks = activity.orca_hooks(hooks_home(tmp_path))
    assert hooks["ok"]
    assert hooks["panes"]["leaf-live"]["provider"] == "codex"
    assert hooks["panes"]["leaf-live"]["state"] == "working"
    assert "ghp_" not in hooks["panes"]["leaf-live"]["prompt"]
    old = hooks["panes"]["leaf-old"]  # ended session: only in the spool
    assert (old["state"], old["prompt"]) == ("done", "/factory-implement CHG-0012-01")
    assert [(e["event"], e["id"]) for e in hooks["subagents"]] == [("SubagentStart", "a1"), ("SubagentStop", "a1")]


def test_missing_or_broken_sources_are_unavailable_not_errors(tmp_path):
    assert activity.orca_hooks(tmp_path) == {"ok": False, "panes": {}, "subagents": []}
    write(tmp_path / ".config/orca/agent-hooks/last-status.json", "{broken")
    assert activity.orca_hooks(tmp_path)["ok"]
    assert activity.claude_subagents(tmp_path, WORKSPACE) == []
    assert activity.codex_sessions(tmp_path, WORKSPACE) == []


def claude_subagent(home, agent, finished, description="Find the helpers"):
    folder = home / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(WORKSPACE)) / "session-1/subagents"
    meta = {"agentType": "Explore", "description": description, "finished": finished}
    write(folder / f"agent-{agent}.meta.json", meta)
    write(folder / f"agent-{agent}.jsonl", json.dumps({"timestamp": "2026-10-18T09:08:26.123Z"}) + "\n")


def test_claude_subagents_of_the_workspace(tmp_path):
    claude_subagent(tmp_path, "b2", finished=False)
    [sub] = activity.claude_subagents(tmp_path, WORKSPACE)
    assert (sub["id"], sub["type"], sub["label"], sub["running"]) == ("b2", "Explore", "Find the helpers", True)
    assert sub["started"] == "2026-10-18T09:08:26Z"
    assert activity.claude_subagents(tmp_path, Path("/elsewhere")) == []


def test_codex_sessions_of_the_workspace(tmp_path):
    folder = tmp_path / ".codex/sessions/2026/10/18"

    def rollout(name, cwd, source):
        return write(folder / f"rollout-{name}.jsonl",
                     json.dumps({"type": "session_meta", "payload": {"id": name, "cwd": cwd, "source": source}}) + "\n")

    rollout("main", str(WORKSPACE), "cli")
    rollout("sub", str(WORKSPACE), {"subagent": {"parent": "main"}})
    rollout("other", "/elsewhere", "cli")
    old = rollout("old", str(WORKSPACE), "cli")
    os.utime(old, (time.time() - 10 * 86400,) * 2)
    found = {s["id"]: s["subagent"] for s in activity.codex_sessions(tmp_path, WORKSPACE)}
    assert found == {"main": False, "sub": True}


def record(terminal="term_lead"):
    return {"attempts": [{"terminal": terminal}], "workspace": {"orca_id": f"r::{WORKSPACE}"}}


def terminal(handle, leaf, connected=True, seconds_ago=5.0, now=1_700_000_100.0):
    return {"handle": handle, "leafId": leaf, "worktreePath": str(WORKSPACE), "title": "✳ Claude Code",
            "connected": connected, "lastOutputAt": (now - seconds_ago) * 1000}


def test_runs_join_terminals_hooks_and_subagents(tmp_path):
    home = hooks_home(tmp_path)
    claude_subagent(home, "a1", finished=True, description="Quality review of CHG-0012-01")
    now = 1_700_000_100.0
    view = {"ok": True, "terminals": [terminal("term_lead", "leaf-old", seconds_ago=3),
                                      terminal("term_rev", "leaf-live", seconds_ago=600),
                                      terminal("term_x", "leaf-none", connected=False),
                                      {**terminal("term_y", "leaf-y"), "worktreePath": "/elsewhere"}]}
    found = activity.runs(WORKSPACE, record(), view, activity.orca_hooks(home), home, now=now)
    agents = [(r["kind"], r["provider"], r["role"], r["state"], r["active"]) for r in found if r["kind"] != "subagent"]
    assert agents == [("agent", "claude", "lead", "done", True), ("agent", "codex", None, "working", False),
                      ("terminal", None, None, "closed", True)]
    [sub] = [r for r in found if r["kind"] == "subagent"]
    assert (sub["label"], sub["state"], sub["detail"]) == ("Quality review of CHG-0012-01", "done", "pass")


def test_liveness_and_missing_workspace_from_one_orca_view():
    view = {"ok": True, "terminals": [terminal("term_lead", "l")], "worktrees": {f"r::{WORKSPACE}": {}}}
    assert activity.liveness(record(), view) == "alive"
    assert activity.liveness(record("term_gone"), view) == "finished"
    assert activity.liveness(record(None), view) == "unknown"
    assert activity.workspace_missing(record(), view) is False
    down = {"ok": False, "terminals": [], "worktrees": {}}
    assert activity.liveness(record(), down) == "unknown"
    assert activity.workspace_missing(record(), down) is None
