##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
Background runner for SQL export (Heidi-style).

This script is executed by pgAdmin's background process executor and must not
import Flask app context. It receives a JSON params file path as argv[1].

It runs:
  - pg_dump (plain SQL) against the source server/database
  - optionally psql to apply the generated SQL to the target server/database
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _env_with_password(base_env: dict, pwd: str | None) -> dict:
    env = dict(base_env)
    if pwd:
        env["PGPASSWORD"] = pwd
    return env


def _run(cmd: list[str], env: dict) -> None:
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    if len(sys.argv) < 2:
        print("Missing params file path", file=sys.stderr)
        return 2

    params_path = sys.argv[1]
    params = _read_json(params_path)

    base_env = os.environ.copy()

    # Source
    src_pwd = base_env.get(params.get("src_pwd_env", ""), "")
    src_conn = params.get("src_conn") or {}

    # Target
    output_type = params.get("output_type")
    tgt_pwd = (
        base_env.get(params.get("tgt_pwd_env", ""), "")
        if output_type == "server"
        else ""
    )
    tgt_conn = params.get("tgt_conn") or {}

    dump_cmd = [
        params["pg_dump"],
        "--host",
        src_conn.get("host") or "",
    ]
    if src_conn.get("port"):
        dump_cmd.extend(["--port", str(src_conn["port"])])
    dump_cmd.extend(["--username", src_conn.get("user") or ""])
    dump_cmd.extend(params.get("pg_dump_args") or [])

    # pg_dump
    print("== Running pg_dump ==")
    _run(dump_cmd, _env_with_password(base_env, src_pwd))

    if output_type != "server":
        print("== SQL export complete (file) ==")
        return 0

    target = params.get("target") or {}
    tgt_db = target.get("database")
    initial_db = target.get("initial_database") or "postgres"

    # If CREATE DATABASE is used, we should start from an existing db
    if params.get("backup_options", {}).get("include_create_database", False):
        psql_db = initial_db
    else:
        psql_db = tgt_db or initial_db

    psql_cmd = [
        params["psql"],
        "--host",
        tgt_conn.get("host") or "",
    ]
    if tgt_conn.get("port"):
        psql_cmd.extend(["--port", str(tgt_conn["port"])])
    psql_cmd.extend(["--username", tgt_conn.get("user") or ""])
    psql_cmd.extend(["--dbname", psql_db])
    psql_cmd.extend(["--set", "ON_ERROR_STOP=on"])
    psql_cmd.extend(["--file", params["dump_file"]])

    print("== Applying SQL on target via psql ==")
    _run(psql_cmd, _env_with_password(base_env, tgt_pwd))

    print("== SQL export complete (applied to server) ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
