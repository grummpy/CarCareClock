"""Command line for CarCareClock. With no subcommand, it serves the local UI."""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import threading
import webbrowser
from datetime import date
from pathlib import Path

from carcareclock.checker_install import install_checker
from carcareclock.db import connect, init_db
from carcareclock.notify import deliver
from carcareclock.paths import data_dir, database_path, defaults_path, repo_root, rules_path
from carcareclock.rules import load_defaults, load_rules
from carcareclock.service import all_items, reminder_lines, seed_demo
from carcareclock.web import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="carcareclock", description="Local car care reminders.")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Open the local web UI (the default).")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--no-notify", action="store_true")

    sub.add_parser("check", help="Print due items and send a desktop notification.")
    sub.add_parser("status", help="Print due and upcoming items.")

    export = sub.add_parser("export-ics", help="Write an .ics file with 7-day alarms.")
    export.add_argument("--output", type=Path, default=Path("carcareclock.ics"))

    install = sub.add_parser(
        "install-checker",
        help="Write a launchd, Task Scheduler, or cron file. Off unless --enable.",
    )
    install.add_argument("kind", choices=("launchd", "task", "cron"))
    install.add_argument(
        "--enable",
        action="store_true",
        help="Register the checker with the OS. Leave this off; it is not the default.",
    )
    install.add_argument(
        "--disable",
        action="store_true",
        help="Remove CarCareClock's cron entry while preserving other entries.",
    )

    args = parser.parse_args(argv)
    command = args.cmd or "serve"
    if command == "serve":
        if args.cmd is None:
            args.port = 0
            args.no_browser = False
            args.no_notify = False
        return cmd_serve(args)
    if command == "check":
        return cmd_check()
    if command == "status":
        return cmd_status()
    if command == "export-ics":
        return cmd_export(args.output)
    if command == "install-checker":
        if args.enable and args.disable:
            parser.error("--enable and --disable cannot be used together")
        return cmd_install(args.kind, args.enable, args.disable)
    parser.print_help()
    return 2


def _prepare():
    rules = load_rules(rules_path())
    defaults = load_defaults(defaults_path())
    conn = connect(database_path())
    init_db(conn)
    seed_demo(conn, defaults)
    return rules, defaults, conn


def cmd_serve(args: argparse.Namespace) -> int:
    rules = load_rules(rules_path())
    defaults = load_defaults(defaults_path())
    secret_path = data_dir() / "secret.key"
    if secret_path.exists():
        secret = secret_path.read_text(encoding="utf-8").strip()
    else:
        secret = secrets.token_hex(32)
        secret_path.write_text(secret, encoding="utf-8")
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
    app = create_app(database_path(), rules, defaults, secret_key=secret)
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"CarCareClock is running at {url}")
    print(rules.verify_with_mva)
    if not args.no_notify:
        cmd_check()
    if not args.no_browser and not os.environ.get("CARCARE_NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    return 0


def cmd_check() -> int:
    rules, defaults, conn = _prepare()
    try:
        lines = reminder_lines(all_items(conn, rules, defaults, date.today()))
    finally:
        conn.close()
    if not lines:
        print("Nothing is due in the reminder window.")
        return 0
    for line in lines:
        print(line)
    deliver(lines)
    return 0


def cmd_status() -> int:
    rules, defaults, conn = _prepare()
    try:
        items = all_items(conn, rules, defaults, date.today())
    finally:
        conn.close()
    for item in items:
        when = item.date_label or "no date"
        print(f"{item.vehicle_name}\t{item.label}\t{item.status}\t{when}\t{item.phrase}")
    return 0


def cmd_export(output: Path) -> int:
    from carcareclock.service import calendar_items, reminder_window_days

    rules, defaults, conn = _prepare()
    try:
        today = date.today()
        items = calendar_items(all_items(conn, rules, defaults, today), today, rules.verify_with_mva)
        window = reminder_window_days(conn)
    finally:
        conn.close()
    from carcareclock.ics_export import build_calendar

    output.write_bytes(build_calendar(items, alarm_days=window))
    print(f"Wrote {output.resolve()} ({len(items)} events, alarm {window} days ahead).")
    return 0


def cmd_install(kind: str, enable: bool, disable: bool = False) -> int:
    if disable and kind != "cron":
        print("--disable is currently supported for cron only.")
        return 2
    if enable:
        action = "enable"
    else:
        action = "disable" if disable else "write"
    try:
        path = install_checker(kind, repo_root(), data_dir(), enable=enable, disable=disable)
    except OSError as exc:
        print(exc)
        return 2
    if action == "enable":
        print("Enabled the background checker.")
    elif action == "disable":
        print("Disabled the CarCareClock cron entry; other cron entries were preserved.")
    else:
        print("Writing the checker file only. It is off by default. Pass --enable to register it.")
    print(path)
    return 0


def _free_port(start: int = 8731) -> int:
    for port in range(start, start + 40):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
