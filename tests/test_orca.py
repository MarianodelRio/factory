import copy

import pytest
from conftest import load_fixture, orca_error

from swfactory import orca
from swfactory.output import EXIT_UNAVAILABLE, FactoryError


def failure(fn, *args):
    with pytest.raises(FactoryError) as exc:
        fn(*args)
    assert exc.value.exit_code == EXIT_UNAVAILABLE
    return exc.value


def test_run_adds_json_and_returns_result(repo, fake_orca):
    result = orca.run(["status"])
    assert result["target"]["kind"] == "local"
    assert fake_orca.calls() == [["status", "--json"]]


def test_run_maps_orca_errors(repo, fake_orca):
    fake_orca.fail("worktree show", code="selector_not_found", message="no such worktree")
    error = failure(orca.run, ["worktree", "show", "--worktree", "id:x"])
    assert error.code == "orca_failed"
    assert error.orca_code == "selector_not_found"
    assert "no such worktree" in error.message


def test_run_non_json_output(repo, fake_orca):
    fake_orca.respond("status", "garbage", exit=0)
    assert failure(orca.run, ["status"]).code == "orca_failed"


def test_orca_not_installed(repo, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert failure(orca.run, ["status"]).code == "orca_unavailable"
    assert failure(orca.check, "1.4.229").code == "orca_unavailable"


def test_check_ok(repo, fake_orca):
    info = orca.check("1.4.229")
    assert info == {"version": "1.4.229", "local": True}


def test_check_old_version(repo, fake_orca):
    error = failure(orca.check, "1.5.0")
    assert error.code == "orca_outdated"
    assert "1.5.0" in error.message


def test_check_version_compares_numbers_not_text(repo, fake_orca):
    fake_orca.respond("version", "1.10.0")
    assert orca.check("1.9.9")["version"] == "1.10.0"


def test_check_runtime_unreachable(repo, fake_orca):
    status = load_fixture("status")
    status["result"]["runtime"]["reachable"] = False
    fake_orca.respond("status", status)
    assert failure(orca.check, "1.4.229").code == "orca_not_running"


def test_check_orca_closed(repo, fake_orca):
    fake_orca.respond("status", orca_error("runtime_unavailable", "Orca is not running"), exit=1)
    error = failure(orca.check, "1.4.229")
    assert error.code == "orca_not_running"
    assert "Orca is not running" in error.message


@pytest.mark.parametrize("variable", ["ORCA_PAIRING_CODE", "ORCA_ENVIRONMENT"])
def test_check_rejects_remote_variables(repo, fake_orca, monkeypatch, variable):
    monkeypatch.setenv(variable, "something")
    assert failure(orca.check, "1.4.229").code == "orca_not_local"


def test_check_rejects_non_local_host(repo, fake_orca):
    status = load_fixture("status")
    status["result"]["target"] = {"kind": "environment", "id": "build-server"}
    fake_orca.respond("status", status)
    assert failure(orca.check, "1.4.229").code == "orca_not_local"


def test_check_missing_command(repo, fake_orca):
    context = load_fixture("agent-context")
    context["commands"] = [c for c in context["commands"] if c["command"] != "worktree set"]
    fake_orca.respond("agent-context", context)
    error = failure(orca.check, "1.4.229")
    assert error.code == "orca_missing_command"
    assert "worktree set" in error.message


def test_check_missing_flag(repo, fake_orca):
    context = copy.deepcopy(load_fixture("agent-context"))
    for c in context["commands"]:
        if c["command"] == "agent launch":
            c["flags"].remove("retry-launch")
    fake_orca.respond("agent-context", context)
    assert "retry-launch" in failure(orca.check, "1.4.229").message


def test_base_branch(repo, fake_orca):
    assert orca.base_branch(repo.root) == "main"
    assert fake_orca.calls()[-1] == ["repo", "show", "--repo", f"path:{repo.root}", "--json"]


@pytest.mark.parametrize(("ref", "branch"), [("origin/develop", "develop"),
                                             ("refs/remotes/origin/release/1.x", "release/1.x"),
                                             ("refs/heads/trunk", "trunk"), ("main", "main")])
def test_base_branch_forms(repo, fake_orca, ref, branch):
    body = load_fixture("repo-show-with-base-ref")
    body["result"]["repo"]["worktreeBaseRef"] = ref
    fake_orca.respond("repo show", body)
    assert orca.base_branch(repo.root) == branch


def test_base_branch_not_set(repo, fake_orca):
    fake_orca.respond_fixture("repo show", "repo-show")
    error = failure(orca.base_branch, repo.root)
    assert error.code == "orca_base_branch_unset"
    assert "set-base-ref" in error.message


def test_base_branch_repo_not_registered(repo, fake_orca):
    fake_orca.respond_fixture("repo show", "repo-show-not-found", exit=1)
    error = failure(orca.base_branch, repo.root)
    assert error.code == "orca_repo_not_registered"


def test_check_short_version_is_padded(repo, fake_orca):
    fake_orca.respond("version", "1.5")
    assert orca.check("1.5.0")["version"] == "1.5"


def test_check_unexpected_status_shape(repo, fake_orca):
    fake_orca.respond("status", {"ok": True, "result": {"something": "else"}})
    assert failure(orca.check, "1.4.229").code == "orca_failed"
