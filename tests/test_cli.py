import json

import pytest

from factory import __version__, cli
from factory.cli import main
from factory.output import FactoryError

# Every command path.
COMMANDS = [
    ["install-skill"],
    ["doctor"],
    ["init"],
    ["design", "register"],
    ["design", "show"],
    ["design", "approve"],
    ["design", "reject"],
    ["task", "list"],
    ["task", "show"],
    ["task", "claim"],
    ["task", "launch"],
    ["task", "checkpoint"],
    ["task", "note"],
    ["task", "block"],
    ["task", "unblock"],
    ["task", "verify"],
    ["task", "submit"],
    ["task", "review"],
    ["task", "finish"],
    ["task", "publish"],
    ["task", "recover"],
    ["memory", "check"],
    ["status"],
]


def run(capsys, argv):
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize("path", COMMANDS)
def test_every_command_has_help(capsys, path):
    with pytest.raises(SystemExit) as exc:
        main([*path, "--help"])
    assert exc.value.code == 0


@pytest.fixture
def outside_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


def test_status_json_prints_one_envelope(capsys, outside_git):
    code, out, _ = run(capsys, ["status", "--json"])
    envelope = json.loads(out)
    assert set(envelope) == {"ok", "error", "warnings"}
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "not_a_git_repo"
    assert envelope["warnings"] == []
    assert code == 3


def test_json_flag_before_subcommand(capsys, outside_git):
    _, out, _ = run(capsys, ["--json", "status"])
    assert json.loads(out)["error"]["code"] == "not_a_git_repo"


def test_usage_error_with_json_is_an_envelope(capsys):
    code, out, _ = run(capsys, ["task", "launch", "CHG-0001-01", "--json"])
    envelope = json.loads(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "usage_error"
    assert code == 2


def test_usage_error_without_json_goes_to_stderr(capsys):
    code, out, err = run(capsys, ["task", "nope"])
    assert code == 2
    assert out == ""
    assert "invalid choice" in err


def test_error_without_json_goes_to_stderr(capsys, monkeypatch):
    def fail(args):
        raise FactoryError("some_error", "it failed")

    monkeypatch.setitem(cli.HANDLERS, "doctor", fail)
    code, out, err = run(capsys, ["doctor"])
    assert code == 1
    assert out == ""
    assert "some_error" in err
