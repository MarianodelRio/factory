"""`factory` command line: argparse subcommands, output and exit codes. No logic lives here."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any, NoReturn

from factory import __version__, design, paths
from factory.output import (
    EXIT_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    FactoryError,
    error_envelope,
    ok_envelope,
    render,
)
from factory.state import TaskStore

Result = tuple[dict[str, Any], list[str]]
Handler = Callable[[argparse.Namespace], Result]


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.prog}: {message}")


def not_implemented(args: argparse.Namespace) -> Result:
    raise FactoryError("not_implemented", f"'{args.command}' is not implemented yet", EXIT_ERROR)


def change_id(value: str) -> str:
    if not design.CHANGE_ID.match(value):
        raise argparse.ArgumentTypeError(f"'{value}' is not a change id (CHG-NNNN)")
    return value


def design_register(args: argparse.Namespace) -> Result:
    if args.change is None:
        return design.reserve_change(paths.changes_dir()), []
    return design.register(args.change, paths.changes_dir()), []


def design_show(args: argparse.Namespace) -> Result:
    return design.show(args.change, paths.changes_dir(), TaskStore(paths.state_dir())), []


def design_approve(args: argparse.Namespace) -> Result:
    if args.message is None:
        typed = input(f"Type {args.change} to approve its current design: ")
        message, method = typed, "terminal"
    else:
        message, method = args.message, "chat"
    return design.approve(args.change, paths.changes_dir(), message, method, paths.main_checkout()), []


def design_reject(args: argparse.Namespace) -> Result:
    return design.reject(args.change, paths.changes_dir(), args.reason, paths.main_checkout()), []


# Command name ("task launch") -> handler. Filled in as tasks are implemented.
HANDLERS: dict[str, Handler] = {
    "design register": design_register,
    "design show": design_show,
    "design approve": design_approve,
    "design reject": design_reject,
}


def build_parser() -> Parser:
    json_flag = Parser(add_help=False)
    json_flag.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="print one JSON object"
    )

    parser = Parser(prog="factory", description="Software Factory CLI.", parents=[json_flag])
    parser.add_argument("--version", action="version", version=f"factory {__version__}")
    groups = parser.add_subparsers(dest="group", required=True, metavar="<command>")

    def command(subparsers: Any, name: str, full_name: str, help_text: str) -> Parser:
        sub: Parser = subparsers.add_parser(name, help=help_text, parents=[json_flag])
        sub.set_defaults(command=full_name)
        return sub

    command(groups, "doctor", "doctor", "analyze the repository without changing it")

    init = command(groups, "init", "init", "prepare the repository for the Factory")
    mode = init.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="show the plan without applying it")
    mode.add_argument("--apply", action="store_true", help="apply the plan")
    mode.add_argument("--restore", metavar="BACKUP", help="restore a backup")

    design = groups.add_parser("design", help="register, show, approve or reject a change")
    design_cmds = design.add_subparsers(dest="action", required=True, metavar="<action>")
    register = command(design_cmds, "register", "design register", "reserve an id, or validate a design")
    register.add_argument("change", nargs="?", type=change_id, help="omit to reserve the next id")
    command(design_cmds, "show", "design show", "show a change").add_argument("change", type=change_id)
    approve = command(design_cmds, "approve", "design approve", "approve a change (base branch only)")
    approve.add_argument("change", type=change_id)
    approve.add_argument("--message", help="the person's literal approval message")
    reject = command(design_cmds, "reject", "design reject", "reject a change")
    reject.add_argument("change", type=change_id)
    reject.add_argument("--reason", required=True)

    task = groups.add_parser("task", help="task lifecycle")
    task_cmds = task.add_subparsers(dest="action", required=True, metavar="<action>")
    command(task_cmds, "list", "task list", "list tasks and their states")
    for name, help_text in (
        ("show", "show a task"),
        ("claim", "claim a task and create its Orca workspace"),
        ("unblock", "return a blocked task to its previous state"),
        ("submit", "move a task to in_review"),
        ("publish", "push the task branch and open a PR"),
    ):
        command(task_cmds, name, f"task {name}", help_text).add_argument("task")

    launch = command(task_cmds, "launch", "task launch", "launch the lead agent in the task workspace")
    launch.add_argument("task")
    launch.add_argument("--agent", required=True, choices=["claude", "codex"])
    launch.add_argument("--model")
    launch.add_argument("--effort")

    checkpoint = command(task_cmds, "checkpoint", "task checkpoint", "record progress, read pending notes")
    checkpoint.add_argument("task")
    checkpoint.add_argument("--done", required=True)
    checkpoint.add_argument("--next", required=True)

    note = command(task_cmds, "note", "task note", "leave a note for the agent")
    note.add_argument("task")
    note.add_argument("--text", required=True)
    note.add_argument("--pause", action="store_true", help="ask the agent to pause")

    block = command(task_cmds, "block", "task block", "move a task to blocked")
    block.add_argument("task")
    block.add_argument("--reason", required=True)

    verify = command(task_cmds, "verify", "task verify", "run checks and acceptance criteria")
    verify.add_argument("task")
    verify.add_argument("--manual", metavar="AC", help="acceptance criterion verified by hand")
    verify.add_argument("--evidence", metavar="FILE", help="evidence file for --manual")

    review = command(task_cmds, "review", "task review", "launch or record a review")
    review.add_argument("task")
    review_mode = review.add_mutually_exclusive_group(required=True)
    review_mode.add_argument("--type", choices=["quality", "conformance"])
    review_mode.add_argument("--record", metavar="FILE", help="reviewer JSON to record")
    review.add_argument("--agent")

    finish = command(task_cmds, "finish", "task finish", "close a task when every gate passes")
    finish.add_argument("task")
    finish.add_argument("--memory", required=True, help='memory summary, or "none"')

    recover = command(task_cmds, "recover", "task recover", "inspect an interrupted task")
    recover.add_argument("task")
    recover.add_argument("--confirm", action="store_true", help="start a new attempt")

    memory = groups.add_parser("memory", help="project memory maintenance")
    memory_cmds = memory.add_subparsers(dest="action", required=True, metavar="<action>")
    command(memory_cmds, "check", "memory check", "check AGENTS.md, decisions and links")

    command(groups, "status", "status", "summary of changes and tasks")
    return parser


def _validate(args: argparse.Namespace) -> None:
    if args.command == "task verify" and (args.manual is None) != (args.evidence is None):
        raise UsageError("factory task verify: --manual and --evidence go together")
    if args.command == "task review" and args.agent and args.record:
        raise UsageError("factory task review: --agent only applies with --type")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv
    try:
        args = build_parser().parse_args(argv)
        _validate(args)
    except UsageError as exc:
        return _emit(error_envelope(FactoryError("usage_error", str(exc), EXIT_USAGE)), as_json, EXIT_USAGE)

    handler = HANDLERS.get(args.command, not_implemented)
    try:
        data, warnings = handler(args)
    except FactoryError as exc:
        return _emit(error_envelope(exc), as_json, exc.exit_code)
    except Exception as exc:  # noqa: BLE001 - last resort: still answer with the contract
        error = FactoryError("unexpected_error", f"{type(exc).__name__}: {exc}", EXIT_ERROR)
        return _emit(error_envelope(error), as_json, EXIT_ERROR)
    return _emit(ok_envelope(data, warnings), as_json, EXIT_OK)


def _emit(envelope: dict[str, Any], as_json: bool, code: int) -> int:
    stream = sys.stdout if as_json or envelope["ok"] else sys.stderr
    print(render(envelope, as_json), file=stream)
    return code


def run() -> None:
    sys.exit(main())
