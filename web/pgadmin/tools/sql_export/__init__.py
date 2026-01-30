##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""
HeidiSQL-style SQL export tool.

This tool is a thin wrapper around pg_dump (SQL output) and optionally applies
the resulting SQL to a target server/database using psql. This matches the
HeidiSQL UX of selecting objects and choosing an output destination, while
reusing pgAdmin's proven pg_dump option set and background process manager.
"""

import json
import os
import secrets

from config import PG_DEFAULT_DRIVER
from flask import current_app, request
from flask_babel import gettext as _
from flask_security import permissions_required

from pgadmin.misc.bgprocess.processes import BatchProcess, IProcessDesc
from pgadmin.model import Server
from pgadmin.tools.user_management.PgAdminPermissions import AllPermissionTypes
from pgadmin.user_login_check import pga_login_required
from pgadmin.utils import (
    PgAdminModule,
    does_utility_exist,
    get_server,
    get_storage_directory,
)
from pgadmin.utils.ajax import bad_request, make_json_response

MODULE_NAME = "sql_export"


class SqlExportModule:
    # This module is registered as a Flask blueprint by ToolsModule.
    LABEL = _("SQL Export")


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, mode=int("700", 8), exist_ok=True)


def _get_effective_host_port(server: Server, manager) -> tuple[str | None, str | None]:
    host = manager.local_bind_host if manager.use_ssh_tunnel else server.host
    port = (
        str(manager.local_bind_port)
        if manager.use_ssh_tunnel
        else (str(server.port) if server.port else None)
    )
    return host, port


class SqlExportMessage(IProcessDesc):
    def __init__(self, *, src_sid: int, src_db: str, target_label: str, bfile: str):
        self.src_sid = src_sid
        self.src_db = src_db
        self.target_label = target_label
        self.bfile = bfile

    @property
    def message(self):
        return _("Exporting SQL from database '%(db)s' to %(target)s") % {
            "db": self.src_db,
            "target": self.target_label,
        }

    def details(self, cmd, args):
        return {
            "message": self.message,
            "cmd": cmd,
            "args": args,
            "object": self.src_db,
            "type": _("SQL Export"),
        }


def _decrypt_server_password(manager, env_key: str) -> tuple[bool, str | None]:
    """
    Decrypt and return server password (if available) to be injected into
    env var `env_key` for the background process.
    """
    # ServerManager.export_password_env() returns False when crypt key missing.
    try:
        res = manager.export_password_env(env_key)
        # export_password_env returns None on success (historical)
        if res is False:
            return False, _("Master password is required to decrypt server password.")
        return True, None
    except Exception as e:
        current_app.logger.exception(e)
        return False, str(e)


def _write_params_file(params: dict) -> str:
    base_dir = os.path.join(get_storage_directory(), "sql_export")
    _safe_mkdir(base_dir)
    token = secrets.token_hex(16)
    path = os.path.join(base_dir, f"job_{token}.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(params, fp)
    return path


def _default_dump_filename(src_db: str) -> str:
    base_dir = os.path.join(get_storage_directory(), "sql_export")
    _safe_mkdir(base_dir)
    token = secrets.token_hex(8)
    return os.path.join(base_dir, f"{src_db}_{token}.sql")


def _validate_connected(manager) -> bool:
    conn = manager.connection()
    return bool(conn and conn.connected())


def _utility_path(manager, operation: str) -> str | None:
    return manager.utility(operation)


def _validate_utility(manager, operation: str) -> str | None:
    utility = _utility_path(manager, operation)
    ret_val = does_utility_exist(utility)
    return ret_val


def _get_server_manager(sid: int):
    from pgadmin.utils.driver import get_driver

    driver = get_driver(PG_DEFAULT_DRIVER)
    return driver.connection_manager(sid)


def _flatten_server_label(server: Server) -> str:
    host = server.host or ""
    port = server.port or ""
    host_port = f"({host}:{port})" if host and port else (f"({host})" if host else "")
    return f"{server.name} {host_port}".strip()


def _build_pg_dump_args(data: dict) -> list[str]:
    """
    Reuse pgAdmin backup argument builder to keep parity with existing options.
    Force output to PLAIN SQL for this tool.
    """
    # Lazy import to avoid circular dependency and keep scope tight.
    from pgadmin.tools.backup.__init__ import _get_args_params_values

    src_server = get_server(data["src_sid"])
    manager = _get_server_manager(src_server.id)
    conn = manager.connection(did=data.get("did"))

    # Ensure plain format for SQL output
    backup_data = dict(data.get("backup_options", {}))
    backup_data["database"] = data["src_db"]
    backup_data["format"] = "plain"
    backup_data["file"] = data["dump_file"]
    backup_data["type"] = "objects"

    # Selected objects come from BackupSchema depChange already (schema/table/...)
    if "objects" in data:
        backup_data["objects"] = data["objects"]
    if "schemas" in data:
        backup_data["schemas"] = data["schemas"]
    if "tables" in data:
        backup_data["tables"] = data["tables"]

    args = _get_args_params_values(
        backup_data,
        conn,
        backup_obj_type="objects",
        backup_file=data["dump_file"],
        server=src_server,
        manager=manager,
    )
    # backup job appends database name as last arg; do same here.
    args.append(data["src_db"])
    return args


class SqlExportPgAdminModule(PgAdminModule):
    LABEL = _("SQL Export")

    def get_exposed_url_endpoints(self):
        return [
            "sql_export.create_job",
            "sql_export.utility_exists",
        ]


blueprint = SqlExportPgAdminModule(MODULE_NAME, __name__)


@blueprint.route("/utility_exists/<int:sid>", endpoint="utility_exists")
@pga_login_required
def utility_exists(sid):
    server = get_server(sid)
    if server is None:
        return make_json_response(success=0, errormsg=_("Server not found."))

    manager = _get_server_manager(server.id)
    if not _validate_connected(manager):
        return make_json_response(
            success=0, errormsg=_("Please connect to the server first.")
        )

    # Need pg_dump for export, psql for applying-to-server
    dump_err = _validate_utility(manager, "backup")
    if dump_err:
        return make_json_response(success=0, errormsg=dump_err)

    sql_err = _validate_utility(manager, "sql")
    if sql_err:
        # Not fatal for file-only export, but we report so UI can warn.
        return make_json_response(success=0, errormsg=sql_err)

    return make_json_response(success=1)


@blueprint.route("/job/<int:sid>", methods=["POST"], endpoint="create_job")
@permissions_required(AllPermissionTypes.tools_backup)
@pga_login_required
def create_job(sid):
    """
    Create a SQL export job. Supports:
    - output_type = file: run pg_dump to a .sql file
    - output_type = server: run pg_dump to temp file and then apply via psql
    """
    data = json.loads(request.data)

    src_server = get_server(sid)
    if src_server is None:
        return bad_request(errormsg=_("Could not find the specified server."))

    src_manager = _get_server_manager(src_server.id)
    if not _validate_connected(src_manager):
        return bad_request(errormsg=_("Please connect to the server first."))

    output_type = (data.get("output_type") or "file").lower()
    src_db = data.get("database")
    if not src_db:
        return bad_request(errormsg=_("Database name is required."))

    dump_utility = _utility_path(src_manager, "backup")
    dump_err = does_utility_exist(dump_utility)
    if dump_err:
        return make_json_response(success=0, errormsg=dump_err)

    # Decide where the dump will be written
    dump_file = data.get("file") if output_type == "file" else None
    if output_type == "file":
        if not dump_file:
            return bad_request(errormsg=_("Please provide a filename."))
    else:
        dump_file = _default_dump_filename(src_db)

    # Target information (only for output_type=server)
    target = data.get("target") or {}
    # Alguns forms enviam chaves "flat" com ponto (ex.: "target.sid").
    target_sid = target.get("sid") or data.get("target.sid") or data.get("target_sid")
    target_db = (
        target.get("database")
        or data.get("target.database")
        or data.get("target_database")
    )
    target_initial_db = (
        target.get("initial_database")
        or data.get("target.initial_database")
        or data.get("target_initial_database")
        or "postgres"
    )

    if output_type == "server":
        if not target_sid:
            return bad_request(errormsg=_("Target server is required."))
        if not target_db and not data.get("backup_options", {}).get(
            "include_create_database", False
        ):
            return bad_request(
                errormsg=_("Target database is required (or enable CREATE DATABASE).")
            )

    # Build parameters for runner
    # We reuse BackupSchema's object selection structure where possible.
    runner_params = {
        "src_sid": sid,
        "src_db": src_db,
        "did": data.get("did"),
        "dump_file": dump_file,
        "backup_options": data,
        "schemas": data.get("schemas", []),
        "tables": data.get("tables", []),
        "objects": data.get("objects"),
        "output_type": output_type,
        "target": {
            "sid": target_sid,
            "database": target_db,
            "initial_database": target_initial_db,
        }
        if output_type == "server"
        else None,
    }

    # Create a params file in storage (avoid huge argv)
    params_path = _write_params_file(runner_params)

    # Prepare BatchProcess: run our Python runner (single BG job)
    runner_script = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "sql_export_runner.py",
    )

    target_label = _("a file")
    if output_type == "server":
        tgt_server = get_server(int(target_sid))
        target_label = _("server '%(server)s' (database '%(db)s')") % {
            "server": _flatten_server_label(tgt_server)
            if tgt_server
            else str(target_sid),
            "db": target_db or target_initial_db,
        }

    # Important: do NOT call set_env_variables() here, because process_executor
    # would set PGPASSWORD for PROCID and that breaks our 2-connection flow.
    p = BatchProcess(
        desc=SqlExportMessage(
            src_sid=sid,
            src_db=src_db,
            target_label=target_label,
            bfile=dump_file,
        ),
        cmd="python",
        args=[runner_script, params_path],
        manager_obj=None,
    )

    # Inject passwords securely via env vars (runner will map per-subprocess)
    src_pwd_key = f"PGA_SQL_EXPORT_SRC_PWD_{p.id}"
    ok, err = _decrypt_server_password(src_manager, src_pwd_key)
    if not ok:
        return make_json_response(success=0, errormsg=err)

    p.env[src_pwd_key] = os.environ.get(src_pwd_key, "")
    runner_params["src_pwd_env"] = src_pwd_key

    if output_type == "server":
        tgt_server = get_server(int(target_sid))
        if tgt_server is None:
            return make_json_response(success=0, errormsg=_("Target server not found."))
        tgt_manager = _get_server_manager(tgt_server.id)
        if not _validate_connected(tgt_manager):
            return bad_request(errormsg=_("Please connect to the target server first."))
        tgt_pwd_key = f"PGA_SQL_EXPORT_TGT_PWD_{p.id}"
        ok, err = _decrypt_server_password(tgt_manager, tgt_pwd_key)
        if not ok:
            return make_json_response(success=0, errormsg=err)
        p.env[tgt_pwd_key] = os.environ.get(tgt_pwd_key, "")
        runner_params["tgt_pwd_env"] = tgt_pwd_key

    # Host/port (ssh tunnel aware)
    src_host, src_port = _get_effective_host_port(src_server, src_manager)
    runner_params["src_conn"] = {
        "host": src_host,
        "port": src_port,
        "user": src_server.username,
    }

    if output_type == "server":
        tgt_server = get_server(int(target_sid))
        tgt_manager = _get_server_manager(tgt_server.id)
        tgt_host, tgt_port = _get_effective_host_port(tgt_server, tgt_manager)
        runner_params["tgt_conn"] = {
            "host": tgt_host,
            "port": tgt_port,
            "user": tgt_server.username,
        }

    # Compute utilities and pg_dump args (reuse backup builder)
    runner_params["pg_dump"] = dump_utility
    runner_params["pg_dump_args"] = _build_pg_dump_args(
        {
            "src_sid": sid,
            "src_db": src_db,
            "did": data.get("did"),
            "dump_file": dump_file,
            "backup_options": data,
            "schemas": data.get("schemas", []),
            "tables": data.get("tables", []),
            "objects": data.get("objects"),
        }
    )

    if output_type == "server":
        tgt_manager = _get_server_manager(int(target_sid))
        runner_params["psql"] = _utility_path(tgt_manager, "sql")
        psql_err = does_utility_exist(runner_params["psql"])
        if psql_err:
            return make_json_response(success=0, errormsg=psql_err)

    # Rewrite params file with complete, derived values
    with open(params_path, "w", encoding="utf-8") as fp:
        json.dump(runner_params, fp)

    try:
        p.start()
    except Exception as e:
        current_app.logger.exception(e)
        return make_json_response(success=0, errormsg=str(e))

    return make_json_response(
        data={"job_id": p.id, "desc": p.desc.message, "success": 1}
    )
