"""Invoke tasks for Zammad helpdesk/ticket system."""

from __future__ import annotations

import json
import logging
import os
import unicodedata
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg2.extensions

import tomllib
from conjuring.grimoire import print_error
from invoke import Context, Exit, task

# --- Constants ---

ZAMMAD_DIR = Path(__file__).parent
MAP_FILE = ZAMMAD_DIR / "migration_map.json"
ERROR_LOG = ZAMMAD_DIR / "migration_errors.log"
TOML_FILE = ZAMMAD_DIR / "zammad.toml"

# Map key used in TOML [states] entries
TOML_STATE_TYPE_KEY = "zammad_type"

# Map key used in migration_map["groups"] for the import group
MIGRATION_MAP_GROUP_KEY = "redmine_import"

# Docker exec prefixes (avoids repetition across c.run() calls)
_PG17 = "docker exec postgres17 psql -U postgres"
_RAILS = "docker exec zammad-railsserver bundle exec"


class _StateType(str, Enum):
    """Zammad built-in ticket state types. Inherits str so members compare/format as plain strings."""

    OPEN = "open"
    CLOSED = "closed"
    PENDING_REMINDER = "pending reminder"
    PENDING_ACTION = "pending action"


class _Priority(str, Enum):
    """Zammad built-in ticket priorities. Inherits str so members compare/format as plain strings."""

    LOW = "1 low"
    NORMAL = "2 normal"
    HIGH = "3 high"


VALID_STATE_TYPES = {t.value for t in _StateType}
PENDING_STATE_TYPES = {_StateType.PENDING_REMINDER.value, _StateType.PENDING_ACTION.value}


def _compose_file(_c: Context) -> str:
    container_apps_dir = os.environ.get("CONTAINER_APPS_DIR", "~/container-apps")
    return f"-f {Path(container_apps_dir).expanduser()}/zammad/compose.yaml"


def _load_toml() -> dict:
    """Load zammad.toml; raise with a helpful message if missing."""
    if not TOML_FILE.exists():
        msg = f"{TOML_FILE} not found. Copy zammad.toml.example to zammad.toml and fill in your values."
        raise FileNotFoundError(msg)
    with TOML_FILE.open("rb") as f:
        return tomllib.load(f)


# --- Setup / lifecycle tasks ---


@task
def zammad_setup(c: Context) -> None:
    """Set up Zammad: create PostgreSQL 17 database and user."""
    db_pass = os.environ.get("ZAMMAD_DB_PASSWORD")

    if not db_pass:
        print_error("ZAMMAD_DB_PASSWORD environment variable is required")
        raise Exit(code=1)

    print("Step 1: Starting PostgreSQL 17...")
    c.run("cd postgres && docker compose up -d postgres17")

    print("\nStep 2: Creating Zammad database and user...")
    c.run(f'{_PG17} -c "CREATE DATABASE zammad;"')
    c.run(f"{_PG17} -c \"CREATE USER zammad WITH PASSWORD '{db_pass}' CREATEDB;\"")
    c.run(f'{_PG17} -c "GRANT ALL PRIVILEGES ON DATABASE zammad TO zammad;"')
    c.run(f'{_PG17} -d zammad -c "GRANT ALL ON SCHEMA public TO zammad;"')

    print("\n✅ Zammad database setup complete!")
    print("\nNext steps:")
    print("  1. cd redis && docker compose up -d")
    print("  2. invoke zammad-up")
    print("  3. Open http://localhost:8008")


@task(help={"pull": "Pull latest Zammad images before starting"})
def zammad_up(c: Context, pull: bool = False) -> None:
    """Start the Zammad stack (requires postgres17 and redis running)."""
    cf = _compose_file(c)

    if pull:
        print("Pulling latest Zammad images...")
        c.run(f"docker compose {cf} pull")

    print("Starting Zammad stack...")
    c.run(f"docker compose {cf} up -d")
    c.run(f"docker compose {cf} logs -f")


@task
def zammad_down(c: Context) -> None:
    """Stop the Zammad stack."""
    cf = _compose_file(c)
    print("Stopping Zammad stack...")
    c.run(f"docker compose {cf} down")


@task
def zammad_wipe(c: Context) -> None:
    """Delete all data created by the Redmine import (tickets, articles, users, groups, custom fields)."""
    if not MAP_FILE.exists():
        print("No migration_map.json found — nothing to wipe.")
        return

    zammad_token = os.environ.get("ZAMMAD_TOKEN", "")
    zammad_url = os.environ.get("ZAMMAD_URL", "http://localhost:8008")
    if not zammad_token:
        print_error("ZAMMAD_TOKEN environment variable is required")
        raise Exit(code=1)

    migration_map = _load_migration_map()
    api = _ZammadAPI(zammad_url, zammad_token, dry_run=c.config.run.dry)

    # Delete in reverse dependency order: articles → tickets → users → groups → custom fields
    total_failed = 0
    total_failed += _wipe_collection(api, "tickets", "tickets", migration_map, "tickets")
    total_failed += _wipe_collection(api, "users", "users", migration_map, "users")
    total_failed += _wipe_collection(api, "groups", "groups", migration_map, "groups")
    total_failed += _wipe_collection(api, "overviews", "overviews", migration_map, "overviews")
    total_failed += _wipe_tags(api, migration_map)
    total_failed += _wipe_collection(api, "custom fields", "object_manager_attributes", migration_map, "custom_fields")

    if not c.config.run.dry:
        if total_failed:
            print(f"\n⚠  {total_failed} deletion(s) failed — migration_map.json kept so you can retry.")
        else:
            MAP_FILE.unlink()
            print("\n✅ migration_map.json deleted.")
            print("✅ Wipe complete. You can now re-run invoke zammad-migrate.")


def _clear_zammad_references(model: str, record_id: int) -> None:
    """Use docker exec + Rails runner to delete all records that reference this object.

    Zammad's Models.references() check prevents API deletion when dependent rows exist
    (e.g. UserGroup memberships, Cti::CallerId entries) that have no dedicated API endpoints.
    """
    import subprocess

    script = (
        f"refs = Models.references({model}, {record_id}); "
        "refs.each { |klass_name, cols| "
        "  klass = klass_name.constantize; "
        "  cols.each_key { |col| klass.where(col => " + str(record_id) + ").destroy_all } "
        "}"
    )
    subprocess.run(
        ["docker", "exec", "zammad-railsserver", "bundle", "exec", "rails", "r", script],
        check=False,
        capture_output=True,
    )


def _wipe_collection(api: _ZammadAPI, label: str, endpoint_prefix: str, migration_map: dict, map_key: str) -> int:
    """Delete a list of Zammad entities by ID; remove each from migration_map on success.

    Returns the number of failures so the caller can decide whether to keep the map file.
    """
    from tqdm import tqdm

    # Build a reverse lookup: zammad_id → redmine_key, so we can remove entries on success.
    # custom_fields values are dicts {"zammad_name": ..., "id": ...}; others are plain int IDs.
    entries: dict = migration_map.get(map_key, {})
    if map_key == "custom_fields":
        id_to_key = {v["id"]: k for k, v in entries.items() if isinstance(v, dict) and "id" in v}
        ids = list(id_to_key)
    else:
        id_to_key = {v: k for k, v in entries.items()}
        ids = list(id_to_key)

    if not ids:
        print(f"No {label} to wipe.")
        return 0

    suffix = " (and their articles)" if label == "tickets" else ""
    deleted = failed = 0
    for zammad_id in tqdm(ids, desc=f"Deleting {label}{suffix}", unit=label[:-1]):
        try:
            api.delete(f"{endpoint_prefix}/{zammad_id}")
            del migration_map[map_key][id_to_key[zammad_id]]
            _save_migration_map(migration_map, api.dry_run)
            deleted += 1
        except _ZammadAPIError as e:
            if e.status == HTTPStatus.NOT_FOUND or "Couldn't find" in str(e):
                # Already gone — treat as success so the map entry is removed and wipe can complete.
                tqdm.write(f"  (i) {label[:-1].capitalize()} {zammad_id} not found (already deleted) — skipping.")
                del migration_map[map_key][id_to_key[zammad_id]]
                _save_migration_map(migration_map, api.dry_run)
                deleted += 1
            elif "object has references" in str(e) and (
                rails_model := {"users": "User", "groups": "Group"}.get(map_key)
            ):
                # Dependent rows (UserGroup memberships, Cti::CallerId, etc.) block the API
                # delete but have no dedicated API endpoints — clear them via Rails, then retry.
                _clear_zammad_references(rails_model, zammad_id)
                try:
                    api.delete(f"{endpoint_prefix}/{zammad_id}")
                    del migration_map[map_key][id_to_key[zammad_id]]
                    _save_migration_map(migration_map, api.dry_run)
                    deleted += 1
                    continue
                except Exception as e2:
                    tqdm.write(f"  ⚠ Could not delete {label[:-1]} {zammad_id} after clearing references: {e2}")
                    failed += 1
            else:
                tqdm.write(f"  ⚠ Could not delete {label[:-1]} {zammad_id}: {e}")
                failed += 1
        except Exception as e:
            tqdm.write(f"  ⚠ Could not delete {label[:-1]} {zammad_id}: {e}")
            failed += 1
    print(f"  {label.capitalize()}: {deleted} deleted, {failed} failed")
    return failed


def _wipe_tags(api: _ZammadAPI, migration_map: dict) -> int:
    """Remove all imported tags from their Zammad tickets.

    Returns the number of failures.
    """
    from tqdm import tqdm

    entries: dict = migration_map.get("tags", {})
    if not entries:
        print("No tags to wipe.")
        return 0

    deleted = failed = 0
    for key, zammad_ticket_id in tqdm(list(entries.items()), desc="Deleting tags", unit="tag"):
        tag_name = key.split(":", 1)[1] if ":" in key else key
        try:
            api.post(
                "tags/remove",
                {"object": "Ticket", "o_id": zammad_ticket_id, "item": tag_name},
            )
            del migration_map["tags"][key]
            _save_migration_map(migration_map, api.dry_run)
            deleted += 1
        except _ZammadAPIError as e:
            if e.status == HTTPStatus.NOT_FOUND or "Couldn't find" in str(e):
                tqdm.write(f"  (i) Tag '{tag_name}' on ticket {zammad_ticket_id} not found — skipping.")
                del migration_map["tags"][key]
                _save_migration_map(migration_map, api.dry_run)
                deleted += 1
            else:
                tqdm.write(f"  ⚠ Could not remove tag '{tag_name}' from ticket {zammad_ticket_id}: {e}")
                failed += 1
        except Exception as e:
            tqdm.write(f"  ⚠ Could not remove tag '{tag_name}' from ticket {zammad_ticket_id}: {e}")
            failed += 1
    print(f"  Tags: {deleted} removed, {failed} failed")
    return failed


@task
def zammad_reindex(c: Context) -> None:
    """Rebuild the Zammad Elasticsearch search index."""
    _import_mode_off(c)
    print("Rebuilding Zammad Elasticsearch index...")
    c.run(f"{_RAILS} rake zammad:searchindex:rebuild")
    print("✅ Reindex complete. Search results may take a few minutes to reflect all tickets.")


def _import_mode_on(c: Context) -> None:
    print("Enabling import mode (backdates timestamps, suppresses notifications)...")
    c.run(f"{_RAILS} rails r \"Setting.set('import_mode', true)\"")
    c.run(f"{_RAILS} rails r \"Setting.set('system_init_done', false)\"")


def _import_mode_off(c: Context) -> None:
    print("Disabling import mode...")
    c.run(f"{_RAILS} rails r \"Setting.set('import_mode', false)\"")
    c.run(f"{_RAILS} rails r \"Setting.set('system_init_done', true)\"")
    c.run(f'{_RAILS} rails r "Rails.cache.clear"')


# --- Migration internals ---


def _load_migration_map() -> dict:
    if MAP_FILE.exists():
        return json.loads(MAP_FILE.read_text())
    return {
        "users": {},
        "groups": {},
        "tickets": {},
        "articles": {},
        "custom_fields": {},
        "states": {},
        "links": {},
        "overviews": {},
        "tags": {},
    }


def _save_migration_map(migration_map: dict, dry_run: bool = False) -> None:
    if not dry_run:
        MAP_FILE.write_text(json.dumps(migration_map, indent=2))


class _CountingHandler(logging.Handler):
    """Counts every log record emitted through it."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def emit(self, _record: logging.LogRecord) -> None:
        self.count += 1


class _PrintErrorHandler(logging.Handler):
    """Forwards each log record to print_error() for consistent CLI styling."""

    def emit(self, record: logging.LogRecord) -> None:
        print_error(self.format(record))


def _md_to_html(text: str) -> str:
    import markdown

    return markdown.markdown(text, extensions=["extra", "nl2br", "sane_lists"])


def _issue_body(description: str | None, issue_id: int, redmine_base_url: str) -> str:
    """Return the HTML body for a ticket: optional Redmine link header + converted description."""
    body = _md_to_html(description or "(no description)")
    if redmine_base_url:
        url = f"{redmine_base_url}/issues/{issue_id}"
        link = f'<p><a href="{url}">{url}</a></p>'
        body = link + "\n" + body
    return body


def _setup_error_logging() -> tuple[logging.Logger, _CountingHandler]:
    logger = logging.getLogger("migration_errors")
    logger.setLevel(logging.ERROR)
    counter = _CountingHandler()
    if not logger.handlers:
        file_handler = logging.FileHandler(ERROR_LOG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        stderr_handler = _PrintErrorHandler()
        stderr_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)
        logger.addHandler(stderr_handler)
        logger.addHandler(counter)
    else:
        # Re-attach counter on subsequent calls (e.g. re-used logger instance).
        logger.addHandler(counter)
    return logger, counter


def _sanitize_field_name(redmine_name: str) -> str:
    # Decompose accented chars (é → e + combining accent) then drop non-ASCII before filtering.
    ascii_name = unicodedata.normalize("NFKD", redmine_name).encode("ascii", "ignore").decode()
    slug = "redmine_" + ascii_name.lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in slug if c.isascii() and (c.isalnum() or c == "_"))


class _ZammadAPIError(Exception):
    """Raised when a Zammad API call returns a non-2xx response."""

    def __init__(self, msg: str, status: int = 0) -> None:
        super().__init__(msg)
        self.status = status


class _ZammadAPI:
    def __init__(self, base_url: str, token: str, dry_run: bool = False) -> None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token token={token}",
                "Content-Type": "application/json",
            }
        )
        retry = Retry(
            total=4,
            backoff_factor=1,  # sleeps 1s, 2s, 4s between retries
            status_forcelist=[HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT],
            allowed_methods={"GET", "POST", "PUT", "DELETE"},
            raise_on_status=False,  # let callers inspect the response
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.dry_run = dry_run

    def get(self, endpoint: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/v1/{endpoint}")
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]

    def search(self, endpoint: str) -> list:
        resp = self.session.get(f"{self.base_url}/api/v1/{endpoint}")
        resp.raise_for_status()
        result = resp.json()
        return result if isinstance(result, list) else []

    def post(self, endpoint: str, data: dict) -> dict:
        if self.dry_run:
            print(f"  [DRY-RUN] POST /api/v1/{endpoint}: {json.dumps(data, default=str)[:200]}")
            return {"id": -1}
        resp = self.session.post(f"{self.base_url}/api/v1/{endpoint}", json=data)
        if not resp.ok:
            msg = f"{resp.status_code} {resp.reason}: {resp.text[:300]}"
            raise _ZammadAPIError(msg, status=resp.status_code)
        return resp.json()

    def put(self, endpoint: str, data: dict) -> dict:
        if self.dry_run:
            print(f"  [DRY-RUN] PUT /api/v1/{endpoint}: {json.dumps(data, default=str)[:200]}")
            return {"id": -1}
        resp = self.session.put(f"{self.base_url}/api/v1/{endpoint}", json=data)
        resp.raise_for_status()
        return resp.json()

    def delete(self, endpoint: str) -> None:
        if self.dry_run:
            print(f"  [DRY-RUN] DELETE /api/v1/{endpoint}")
            return
        resp = self.session.delete(f"{self.base_url}/api/v1/{endpoint}")
        if not resp.ok:
            msg = f"{resp.status_code} {resp.reason}: {resp.text[:300]}"
            raise _ZammadAPIError(msg, status=resp.status_code)


def _connect_redmine_db(host: str, port: int, dbname: str, user: str, password: str) -> psycopg2.extensions.connection:
    import psycopg2

    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def _tags_table_exists(conn) -> str | None:
    """Return the tags table name if a supported tags plugin is installed, else None."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name IN ('tags', 'additional_tags')
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_name LIMIT 1
        """)
        row = cur.fetchone()
        return row[0] if row else None


def _read_redmine_users(conn) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT u.id, u.login, u.firstname, u.lastname, u.status,
                   ea.address AS mail
            FROM users u
            LEFT JOIN email_addresses ea
                   ON ea.user_id = u.id AND ea.is_default = true
            WHERE u.type = 'User'
            ORDER BY u.id
        """)
        return cur.fetchall()


def _read_redmine_custom_fields(conn) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, name, field_format, possible_values, is_required, default_value
            FROM custom_fields
            WHERE type = 'IssueCustomField'
            ORDER BY id
        """)
        return cur.fetchall()


def _read_redmine_trackers(conn) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT id, name FROM trackers ORDER BY id")
        return cur.fetchall()


def _read_redmine_issues(conn) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT i.id, i.subject, i.description, i.created_on, i.updated_on,
                   i.due_date, i.author_id, i.assigned_to_id, i.parent_id,
                   i.tracker_id,
                   s.name AS status_name, s.is_closed,
                   p.name AS priority_name,
                   t.name AS tracker_name
            FROM issues i
            JOIN issue_statuses s ON i.status_id = s.id
            JOIN enumerations p ON i.priority_id = p.id
            JOIN trackers t ON i.tracker_id = t.id
            ORDER BY i.id
        """)
        return cur.fetchall()


def _read_redmine_journals(conn, issue_id: int) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT j.id, j.user_id, j.notes, j.created_on
            FROM journals j
            WHERE j.journalized_id = %s
              AND j.journalized_type = 'Issue'
              AND j.notes IS NOT NULL
              AND j.notes != ''
            ORDER BY j.created_on
        """,
            (issue_id,),
        )
        return cur.fetchall()


def _read_redmine_custom_values(conn, issue_id: int) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT cf.name, cv.value
            FROM custom_values cv
            JOIN custom_fields cf ON cv.custom_field_id = cf.id
            WHERE cv.customized_id = %s
              AND cv.customized_type = 'Issue'
              AND cv.value IS NOT NULL
              AND cv.value != ''
        """,
            (issue_id,),
        )
        return cur.fetchall()


def _read_redmine_tags_bulk(conn, tags_table: str) -> dict[int, list[str]]:
    """Return {issue_id: [tag_name, ...]} for all issues via the tags plugin tables."""
    import psycopg2.extras

    taggings_table = "taggings" if tags_table == "tags" else "additional_taggings"
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"""
            SELECT tg.taggable_id AS issue_id, t.name AS tag_name
            FROM {tags_table} t
            JOIN {taggings_table} tg ON tg.tag_id = t.id
            WHERE tg.taggable_type = 'Issue'
              AND tg.context = 'tags'
            ORDER BY tg.taggable_id, t.name
        """)  # noqa: S608 — table name comes from our own pg_tables detection, not user input
        result: dict[int, list[str]] = {}
        for row in cur.fetchall():
            result.setdefault(row["issue_id"], []).append(row["tag_name"])
        return result


def _find_tags_custom_field_id(conn, cf_name: str) -> int | None:
    """Return the id of the IssueCustomField with the given name (list type), or None if absent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM custom_fields
            WHERE type = 'IssueCustomField'
              AND field_format = 'list'
              AND lower(name) = lower(%s)
            LIMIT 1
        """,
            (cf_name,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _read_tags_from_custom_field(conn, tags_cf_id: int) -> dict[int, list[str]]:
    """Return {issue_id: [tag_value, ...]} by reading multi-valued custom_values rows."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT customized_id AS issue_id, value AS tag_name
            FROM custom_values
            WHERE custom_field_id = %s
              AND customized_type = 'Issue'
              AND value IS NOT NULL
              AND value <> ''
            ORDER BY customized_id, value
        """,
            (tags_cf_id,),
        )
        result: dict[int, list[str]] = {}
        for row in cur.fetchall():
            result.setdefault(row["issue_id"], []).append(row["tag_name"])
        return result


def _resolve_state_name(status_name: str, is_closed: bool, due_date, state_map: dict) -> str:
    """Return the Zammad state name to use for a given Redmine status."""
    # Always prefer an exact name match in the TOML first, regardless of open/closed.
    if status_name in state_map:
        return status_name
    # No explicit mapping — fall back to type-based heuristics.
    if is_closed:
        return _StateType.CLOSED.value
    if due_date:
        for name, cfg in state_map.items():
            if cfg.get("zammad_type") == _StateType.PENDING_REMINDER.value:
                return name
        return _StateType.PENDING_REMINDER.value
    return _StateType.OPEN.value


# --- Migration steps ---


def _migrate_states(conn, api: _ZammadAPI, migration_map: dict, toml: dict, error_log: logging.Logger) -> None:
    """Create Zammad ticket states matching Redmine statuses (from TOML config)."""
    state_map = toml.get("states", {})
    if not state_map:
        print("\nNo [states] config in zammad.toml — skipping state creation.")
        return

    # Build redmine_status_name → redmine_status_id lookup so we can store a
    # "redmine_status_<id>" → zammad_id index for use by the overviews migration.
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM issue_statuses")
        redmine_status_name_to_id: dict[str, str] = {row[1]: str(row[0]) for row in cur.fetchall()}

    # Derive state_type name→id from existing states (no dedicated /ticket_state_types endpoint).
    # ?expand=true returns state_type as a plain string name alongside state_type_id.
    existing_states = api.get("ticket_states?expand=true")
    state_type_id_map = {s["state_type"]: s["state_type_id"] for s in existing_states if "state_type" in s}

    print(f"\nCreating {len(state_map)} ticket states...")
    migrated = skipped = 0

    for status_name, cfg in state_map.items():
        state_key = f"state_{status_name}"
        redmine_status_id = redmine_status_name_to_id.get(status_name)
        redmine_key = f"redmine_status_{redmine_status_id}" if redmine_status_id else None

        if state_key in migration_map["states"]:
            # Backfill the redmine_status_<id> key if it was added after the initial migration.
            if redmine_key and redmine_key not in migration_map["states"]:
                migration_map["states"][redmine_key] = migration_map["states"][state_key]
            skipped += 1
            continue

        zammad_type = cfg.get(TOML_STATE_TYPE_KEY, _StateType.OPEN.value)
        if zammad_type not in VALID_STATE_TYPES:
            error_log.error(f"State '{status_name}': unknown zammad_type '{zammad_type}'")
            continue

        state_type_id = state_type_id_map.get(zammad_type)
        if not state_type_id:
            error_log.error(f"State '{status_name}': state type '{zammad_type}' not found in Zammad")
            continue

        state_payload = {
            "name": status_name,
            "state_type_id": state_type_id,
            "active": True,
            "default_create": True,
            "default_follow_up": True,
        }
        try:
            result = api.post("ticket_states", state_payload)
            zammad_state_id = result["id"]
            migrated += 1
        except _ZammadAPIError:
            # State already exists — fetch and update it so default_create/follow_up are set.
            existing = api.get("ticket_states")
            match = next((s for s in existing if s["name"] == status_name), None)
            if match:
                api.put(f"ticket_states/{match['id']}", {"default_create": True, "default_follow_up": True})
                zammad_state_id = match["id"]
                migrated += 1
            else:
                error_log.error(f"State '{status_name}': creation failed and state not found by name")
                continue

        migration_map["states"][state_key] = zammad_state_id
        if redmine_key:
            migration_map["states"][redmine_key] = zammad_state_id

    print(f"  States: {migrated} created/found, {skipped} skipped (already done)")
    _save_migration_map(migration_map, api.dry_run)


def _migrate_users(conn, api: _ZammadAPI, migration_map: dict, error_log: logging.Logger) -> None:
    users = _read_redmine_users(conn)
    print(f"\nMigrating {len(users)} users...")
    migrated = skipped = 0

    updated = 0
    for user in users:
        redmine_id = str(user["id"])
        login = user["login"] or f"redmine_user_{user['id']}"
        email = user["mail"] or f"redmine_user_{user['id']}@migration.local"

        if redmine_id in migration_map["users"]:
            # User already migrated — update email in case it was missing on the first run.
            if user["mail"]:
                zammad_id = migration_map["users"][redmine_id]
                try:
                    api.put(f"users/{zammad_id}", {"email": email})
                    updated += 1
                except Exception as e:
                    error_log.error(f"User {user['id']} ({login}) email update: {e}")
            skipped += 1
            continue

        try:
            result = api.post(
                "users",
                {
                    "login": login,
                    "firstname": user["firstname"] or "Unknown",
                    "lastname": user["lastname"] or "User",
                    "email": email,
                    "active": user["status"] == 1,
                    "roles": ["Agent", "Customer"],
                },
            )
        except _ZammadAPIError:
            # User already exists in Zammad — fetch by login to get their ID.
            all_users = api.search(f"users/search?query=login:{login}&limit=1")
            match = next((u for u in all_users if u.get("login") == login), None)
            if not match:
                error_log.error(f"User {user['id']} ({login}): creation failed and user not found by login")
                continue
            result = match
        except Exception as e:
            error_log.error(f"User {user['id']} ({login}): {e}")
            continue
        migration_map["users"][redmine_id] = result["id"]
        migrated += 1

    update_note = f", {updated} email updates" if updated else ""
    print(f"  Users: {migrated} migrated, {skipped} skipped{update_note}")
    _save_migration_map(migration_map, api.dry_run)


def _migrate_group(conn, api: _ZammadAPI, migration_map: dict, toml: dict, error_log: logging.Logger) -> None:
    import_group = toml.get("import_group", "Redmine Import")

    if MIGRATION_MAP_GROUP_KEY not in migration_map["groups"]:
        print(f"\nCreating group '{import_group}'...")
        try:
            result = api.post("groups", {"name": import_group, "active": True})
        except _ZammadAPIError:
            # Group already exists in Zammad (e.g. partial previous run) — fetch its ID by name.
            print(f"  Group '{import_group}' already exists in Zammad, fetching existing ID...")
            groups = api.get("groups")
            match = next((g for g in groups if g["name"] == import_group), None)
            if not match:
                msg = f"Group '{import_group}' creation failed and could not be found by name"
                error_log.error(msg)
                raise _ZammadAPIError(msg) from None
            result = match
        migration_map["groups"][MIGRATION_MAP_GROUP_KEY] = result["id"]
        _save_migration_map(migration_map, api.dry_run)

    parent_group_id = migration_map["groups"][MIGRATION_MAP_GROUP_KEY]

    # Create one child group per Redmine tracker (issue type), nested under the import group.
    trackers = _read_redmine_trackers(conn)
    print(f"  Creating {len(trackers)} tracker groups...")
    for tracker in trackers:
        tracker_key = f"tracker_{tracker['id']}"
        if tracker_key in migration_map["groups"]:
            continue
        try:
            result = api.post("groups", {"name": tracker["name"], "parent_id": parent_group_id, "active": True})
        except _ZammadAPIError:
            groups = api.get("groups")
            full_name = f"{import_group}::{tracker['name']}"
            match = next((g for g in groups if g["name"] == full_name), None)
            if not match:
                error_log.error(f"Tracker group '{tracker['name']}' creation failed and not found by name")
                continue
            result = match
        migration_map["groups"][tracker_key] = result["id"]
    _save_migration_map(migration_map, api.dry_run)

    # Collect all group IDs users must belong to: parent + all tracker child groups.
    all_group_ids = [parent_group_id] + [
        migration_map["groups"][f"tracker_{t['id']}"]
        for t in trackers
        if f"tracker_{t['id']}" in migration_map["groups"]
    ]

    # Ensure every migrated user (including API token user) is a member of all groups.
    # Zammad rejects owner_id or customer_id for users not in the ticket's group.
    user_ids_to_add = list(migration_map["users"].values())
    me = api.get("users/me")
    user_ids_to_add.append(me["id"])
    print(f"  Ensuring {len(user_ids_to_add)} users are members of {len(all_group_ids)} groups...")
    for uid in user_ids_to_add:
        user = api.get(f"users/{uid}")
        current_groups = dict(user.get("group_ids", {}))
        new_entries = {
            gid: ["full"] for gid in all_group_ids if gid not in current_groups and str(gid) not in current_groups
        }
        if new_entries:
            api.put(f"users/{uid}", {"group_ids": {**current_groups, **new_entries}})


def _migrate_custom_fields(
    conn, api: _ZammadAPI, migration_map: dict, error_log: logging.Logger, skip_cf_id: int | None = None
) -> None:
    fields = _read_redmine_custom_fields(conn)
    print(f"\nMigrating {len(fields)} custom field definitions...")
    migrated = skipped = 0

    # Zammad data_type mapping from Redmine field_format.
    format_map = {
        "string": "input",
        "text": "textarea",
        "int": "integer",
        "float": "input",
        "date": "date",
        "bool": "boolean",
        "list": "select",
        "link": "input",
    }
    # Required data_option defaults per Zammad data_type (API rejects fields without these).
    default_data_option: dict[str, dict] = {
        "input": {"default": "", "maxlength": 255, "null": True, "type": "text"},
        "textarea": {"default": "", "rows": 4, "null": True},
        "integer": {"default": None, "min": 0, "max": 999999, "null": True},
        "boolean": {"default": False, "null": True},
        "date": {"diff": 0, "null": True},
        "datetime": {"diff": 0, "null": True},
        "select": {"default": "", "nulloption": True, "null": True, "options": {}, "relation": ""},
    }

    for field in fields:
        redmine_id = str(field["id"])
        if skip_cf_id is not None and field["id"] == skip_cf_id:
            print(f"  Skipping '{field['name']}' (id={field['id']}) — migrated as native Zammad tags.")
            skipped += 1
            continue
        if redmine_id in migration_map["custom_fields"]:
            skipped += 1
            continue

        zammad_name = _sanitize_field_name(field["name"])
        data_type = format_map.get(field["field_format"], "input")

        object_data = {
            "name": zammad_name,
            "display": field["name"],
            "data_type": data_type,
            "object": "Ticket",
            "active": True,
            "position": 900 + int(redmine_id),
            "data_option": dict(default_data_option.get(data_type, {})),
            "screens": {
                "create_middle": {"ticket.agent": {"shown": True}},
                "edit": {"ticket.agent": {"shown": True}},
            },
        }

        if data_type == "select" and field["possible_values"]:
            try:
                import yaml

                values = yaml.safe_load(field["possible_values"])
                if isinstance(values, list):
                    object_data["data_option"] = {
                        "options": {v: v for v in values},
                        "default": field["default_value"] or "",
                        "nulloption": True,
                        "null": True,
                    }
            except Exception:
                error_log.debug("Could not parse possible_values for field '%s'", field["name"])

        try:
            result = api.post("object_manager_attributes", object_data)
        except _ZammadAPIError:
            # Field already exists — fetch all attributes and filter by object type + name.
            all_attrs = api.get("object_manager_attributes")
            match = next((a for a in all_attrs if a.get("object") == "Ticket" and a.get("name") == zammad_name), None)
            if not match:
                error_log.error(f"Custom field {field['id']} ({field['name']}): creation failed and field not found")
                continue
            result = match
        except Exception as e:
            error_log.error(f"Custom field {field['id']} ({field['name']}): {e}")
            continue
        migration_map["custom_fields"][redmine_id] = {"zammad_name": zammad_name, "id": result.get("id", -1)}
        migrated += 1

    if migrated > 0 and not api.dry_run:
        print("  Applying object attribute changes in Zammad...")
        try:
            api.post("object_manager_attributes_execute_migrations", {})
        except Exception as e:
            error_log.error(f"Failed to execute object manager migration: {e}")

    print(f"  Custom fields: {migrated} migrated, {skipped} skipped")
    _save_migration_map(migration_map, api.dry_run)


def _resolve_default_customer(
    conn, api: _ZammadAPI, toml: dict, migration_map: dict, error_log: logging.Logger
) -> int | None:
    """Return the Zammad user ID for default_customer_login from TOML, or None if not configured.

    Checks the migration map first (for migrated Redmine users), then falls back to the API
    search (for pre-existing Zammad users like the built-in admin).
    """
    login = toml.get("default_customer_login", "")
    if not login:
        return None

    # Try to find the Redmine user ID for this login, then look it up in the migration map.
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE login = %s AND type = 'User' LIMIT 1", (login,))
        row = cur.fetchone()
    if row:
        zammad_id = migration_map["users"].get(str(row[0]))
        if zammad_id:
            return zammad_id

    # Fall back to searching Zammad directly (e.g. built-in admin not in the migration map).
    results = api.search(f"users/search?query=login:{login}&limit=1")
    match = next((u for u in results if u.get("login") == login), None)
    if not match:
        error_log.error(f"default_customer_login '{login}' not found in Zammad")
        return None
    return match["id"]


def _migrate_tickets(
    conn,
    api: _ZammadAPI,
    migration_map: dict,
    toml: dict,
    tags_by_issue: dict[int, list[str]],
    error_log: logging.Logger,
    tags_cf_id: int | None = None,
    tags_cf_name: str = "Tags",
) -> None:
    group_id = migration_map["groups"].get(MIGRATION_MAP_GROUP_KEY)
    if not group_id:
        error_log.error("No group_id in migration_map — group migration must have failed. Aborting ticket migration.")
        return

    default_customer_id = _resolve_default_customer(conn, api, toml, migration_map, error_log)

    from tqdm import tqdm

    issues = _read_redmine_issues(conn)
    print(f"\nMigrating {len(issues)} issues → tickets...")
    migrated = skipped = 0
    state_map = toml.get("states", {})
    priority_map = toml.get("priorities", {})
    pending_fallback = toml.get("pending_time_fallback", "2099-12-31T00:00:00Z")
    redmine_base_url = toml.get("redmine_url", "").rstrip("/")

    repaired = 0
    for issue in tqdm(issues, desc="Migrating tickets", unit="ticket"):
        redmine_id = str(issue["id"])

        custom_values = _read_redmine_custom_values(conn, issue["id"])
        custom_fields_data: dict = {}
        for cv in custom_values:
            if tags_cf_id is not None and cv["name"].lower() == tags_cf_name.lower():
                continue  # Already included via tags_by_issue as native Zammad tags
            custom_fields_data[_sanitize_field_name(cv["name"])] = cv["value"]

        if redmine_id in migration_map["tickets"]:
            # Ticket already migrated — repair custom field values in case they were dropped
            # (e.g. if the ticket was created before execute_migrations ran and activated fields).
            if custom_fields_data:
                zammad_id = migration_map["tickets"][redmine_id]
                try:
                    api.put(f"tickets/{zammad_id}", custom_fields_data)
                    repaired += 1
                except Exception as e:
                    error_log.error(f"Issue {issue['id']} repair custom fields: {e}")
            skipped += 1
            continue

        customer_id = migration_map["users"].get(str(issue["author_id"])) or default_customer_id
        owner_id = migration_map["users"].get(str(issue["assigned_to_id"])) if issue["assigned_to_id"] else None

        state_name = _resolve_state_name(issue["status_name"], issue["is_closed"], issue["due_date"], state_map)
        state_type = state_map.get(state_name, {}).get(TOML_STATE_TYPE_KEY, _StateType.OPEN.value)
        priority = priority_map.get(issue["priority_name"], _Priority.NORMAL)

        created_at = issue["created_on"].isoformat() if issue["created_on"] else None
        updated_at = issue["updated_on"].isoformat() if issue["updated_on"] else None

        tracker_group_id = migration_map["groups"].get(f"tracker_{issue['tracker_id']}", group_id)
        ticket_data = {
            "title": issue["subject"],
            "group_id": tracker_group_id,
            "customer_id": customer_id,
            "owner_id": owner_id,
            "state": state_name,
            "priority": priority,
            "article": {
                "subject": issue["subject"],
                "body": _issue_body(issue["description"], issue["id"], redmine_base_url),
                "content_type": "text/html",
                "type": "note",
                "internal": False,
            },
        }

        if created_at:
            ticket_data["created_at"] = created_at
            ticket_data["article"]["created_at"] = created_at
        if updated_at:
            ticket_data["updated_at"] = updated_at

        if state_type in PENDING_STATE_TYPES:
            due = issue["due_date"]
            ticket_data["pending_time"] = due.isoformat() if due else pending_fallback

        tags = tags_by_issue.get(issue["id"], [])
        if tags:
            ticket_data["tags"] = ",".join(tags)

        ticket_data.update(custom_fields_data)

        try:
            result = api.post("tickets", ticket_data)
            zammad_ticket_id = result["id"]
            migration_map["tickets"][redmine_id] = zammad_ticket_id
            for tag in tags:
                migration_map.setdefault("tags", {})[f"{redmine_id}:{tag}"] = zammad_ticket_id
            migrated += 1
            if migrated % 50 == 0:
                _save_migration_map(migration_map, api.dry_run)
        except Exception as e:
            error_log.error(f"Issue {issue['id']} ({issue['subject'][:50]}): {e}")

    repair_note = f", {repaired} custom-field repairs" if repaired else ""
    print(f"  Tickets: {migrated} migrated, {skipped} skipped{repair_note}")
    _save_migration_map(migration_map, api.dry_run)


def _migrate_articles(conn, api: _ZammadAPI, migration_map: dict, error_log: logging.Logger) -> None:
    from tqdm import tqdm

    print("\nMigrating journal entries → articles...")
    migrated = skipped = 0

    for redmine_issue_id, zammad_ticket_id in tqdm(
        migration_map["tickets"].items(), desc="Migrating articles", unit="ticket"
    ):
        journals = _read_redmine_journals(conn, int(redmine_issue_id))

        for journal in journals:
            article_key = f"{redmine_issue_id}_{journal['id']}"
            if article_key in migration_map["articles"]:
                skipped += 1
                continue

            created_at = journal["created_on"].isoformat() if journal["created_on"] else None

            article_data: dict = {
                "ticket_id": zammad_ticket_id,
                "body": _md_to_html(journal["notes"]),
                "content_type": "text/html",
                "type": "note",
                "internal": False,
            }
            if created_at:
                article_data["created_at"] = created_at

            try:
                result = api.post("ticket_articles", article_data)
                migration_map["articles"][article_key] = result["id"]
                migrated += 1
            except Exception as e:
                error_log.error(f"Journal {journal['id']} on issue {redmine_issue_id}: {e}")

    print(f"  Articles: {migrated} migrated, {skipped} skipped")
    _save_migration_map(migration_map, api.dry_run)


def _migrate_links(conn, api: _ZammadAPI, migration_map: dict, error_log: logging.Logger) -> None:
    """Create parent/child links in Zammad for Redmine issues that have a parent_id."""
    import psycopg2.extras
    from tqdm import tqdm

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, parent_id FROM issues
            WHERE parent_id IS NOT NULL
            ORDER BY id
        """)
        parent_rows = cur.fetchall()

    if not parent_rows:
        return

    # Only process pairs where both sides were successfully migrated.
    pairs = [
        (row["id"], row["parent_id"])
        for row in parent_rows
        if str(row["id"]) in migration_map["tickets"] and str(row["parent_id"]) in migration_map["tickets"]
    ]
    if not pairs:
        print("\nNo parent/child links to migrate (no matching ticket pairs in map).")
        return

    print(f"\nMigrating {len(pairs)} parent/child links...")

    # Bulk-fetch Zammad ticket numbers for all involved ticket IDs (one request per 100 IDs).
    # The links/add API requires the source ticket's display number, not its internal ID.
    zammad_ids_needed = {migration_map["tickets"][str(child)] for child, _ in pairs} | {
        migration_map["tickets"][str(parent)] for _, parent in pairs
    }
    id_to_number: dict[int, str] = {}
    for zammad_id in zammad_ids_needed:
        try:
            t = api.get(f"tickets/{zammad_id}")
            id_to_number[zammad_id] = t["number"]
        except Exception as e:
            error_log.error(f"Could not fetch ticket number for Zammad ticket {zammad_id}: {e}")

    migrated = skipped = 0
    for redmine_child_id, redmine_parent_id in tqdm(pairs, desc="Migrating links", unit="link"):
        link_key = f"{redmine_child_id}_{redmine_parent_id}"
        if link_key in migration_map.get("links", {}):
            skipped += 1
            continue

        zammad_parent_id = migration_map["tickets"][str(redmine_parent_id)]
        zammad_child_id = migration_map["tickets"][str(redmine_child_id)]
        parent_number = id_to_number.get(zammad_parent_id)
        if not parent_number:
            error_log.error(f"Issue {redmine_child_id}: parent ticket number not available, skipping link.")
            continue

        try:
            api.post(
                "links/add",
                {
                    "link_type": "parent",
                    "link_object_source": "Ticket",
                    "link_object_source_number": parent_number,
                    "link_object_target": "Ticket",
                    "link_object_target_value": zammad_child_id,
                },
            )
            migration_map.setdefault("links", {})[link_key] = True
            migrated += 1
            if migrated % 50 == 0:
                _save_migration_map(migration_map, api.dry_run)
        except Exception as e:
            error_log.error(f"Issue {redmine_child_id} → parent {redmine_parent_id}: {e}")

    print(f"  Links: {migrated} migrated, {skipped} skipped")
    _save_migration_map(migration_map, api.dry_run)


def _read_redmine_queries(conn) -> list:
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, name, filters, sort_criteria, group_by, user_id, visibility
            FROM queries
            WHERE type = 'IssueQuery'
            ORDER BY id
        """)
        return cur.fetchall()


def _parse_redmine_filters(
    filters_yaml: str | None,
    migration_map: dict,
    toml: dict,
    error_log: logging.Logger,
    query_name: str,
) -> dict:
    """Convert Redmine filter YAML into a Zammad overview condition dict.

    Supported field mappings:
      status_id       → ticket.state_id   (operators: =, !, o)
      assigned_to_id  → ticket.owner_id   (operator: =)
      tracker_id      → ticket.group_id   (operator: =, mapped via tracker_N group keys)
      due_date        → ticket.pending_time (operators: !*, =)
      cf_N            → ticket.<zammad_name> (operator: =, !)

    Unsupported fields (child_id, project_id, etc.) are silently skipped.
    """
    import yaml

    if not filters_yaml or filters_yaml.strip() in ("---", "--- {}"):
        return {}

    try:
        raw: dict = yaml.safe_load(filters_yaml) or {}
    except Exception as e:
        error_log.error(f"Overview '{query_name}': could not parse filters YAML: {e}")
        return {}

    # Ruby YAML serialises symbol keys with a leading ":" — strip it for all keys/sub-keys.
    def _strip(d: dict) -> dict:
        return {k.lstrip(":"): v for k, v in d.items()}

    # Build reverse maps for fast lookups.
    # state_name → zammad_state_id  (from migration_map["states"])
    state_map_toml: dict = toml.get("states", {})
    # Redmine status_id → state_name  (from TOML ordering; we stored state_N keys)
    # We need Redmine status_id → Zammad state_id.  The migration_map stores
    # {"states": {"state_<name>": <zammad_id>}}, so we build name→id first.
    zammad_state_name_to_id: dict[str, int] = {
        k.removeprefix("state_"): v for k, v in migration_map.get("states", {}).items()
    }
    # We also need Redmine status_id → state_name.  Query the DB-agnostic way: rely on
    # the TOML state list — but we can't query the DB here.  Instead we note that the
    # migration_map["states"] keys are "state_<redmine_status_name>", and we need
    # redmine_status_id → name.  We can only do that if we pass the DB or read from the map.
    # Simplest: accept that we can only resolve state IDs that appear literally in
    # migration_map["states"] keys.  For the "o" (open) operator we just emit all
    # non-closed state names.
    closed_state_names = {n for n, cfg in state_map_toml.items() if cfg.get("zammad_type") == "closed"}
    open_state_ids = [str(v) for k, v in zammad_state_name_to_id.items() if k not in closed_state_names]

    # tracker_N group key → zammad_group_id
    tracker_group_ids: dict[str, int] = {
        k: v for k, v in migration_map.get("groups", {}).items() if k.startswith("tracker_")
    }

    # Redmine cf_N → zammad_name (from migration_map["custom_fields"])
    cf_zammad_name: dict[str, str] = {
        f"cf_{rid}": info["zammad_name"]
        for rid, info in migration_map.get("custom_fields", {}).items()
        if isinstance(info, dict) and "zammad_name" in info
    }

    # Operator mapping: Redmine → Zammad
    op_map = {
        "=": "is",
        "!": "is not",
        "~": "contains",
        "!~": "contains not",
        "*": None,  # "any" — omit the condition
        "!*": "is not",  # "none" — is not + empty value list means "not set"
    }

    condition: dict = {}

    for field, raw_filter in raw.items():
        if not isinstance(raw_filter, dict):
            continue
        f = _strip(raw_filter)
        operator_raw: str = str(f.get("operator", "="))
        values: list = f.get("values") or []
        if not isinstance(values, list):
            values = [values]
        values = [str(v) for v in values if v is not None and str(v) != ""]

        # --- status_id ---
        if field == "status_id":
            if operator_raw == "o":
                # Open issues: all non-closed states we know about.
                if open_state_ids:
                    condition["ticket.state_id"] = {"operator": "is", "value": open_state_ids}
            elif operator_raw == "c":
                closed_ids = [str(v) for k, v in zammad_state_name_to_id.items() if k in closed_state_names]
                if closed_ids:
                    condition["ticket.state_id"] = {"operator": "is", "value": closed_ids}
            elif operator_raw in ("=", "!") and values:
                zammad_op = op_map[operator_raw]
                # Resolve Redmine status IDs → Zammad state IDs via the redmine_status_<id>
                # index written by _migrate_states.
                zammad_ids = [
                    str(migration_map["states"][f"redmine_status_{rid}"])
                    for rid in values
                    if f"redmine_status_{rid}" in migration_map["states"]
                ]
                unresolved = [rid for rid in values if f"redmine_status_{rid}" not in migration_map["states"]]
                if unresolved:
                    error_log.warning(f"Overview '{query_name}': status IDs {unresolved} not in map — skipped.")
                if zammad_ids:
                    condition["ticket.state_id"] = {"operator": zammad_op, "value": zammad_ids}
            continue

        # --- assigned_to_id ---
        if field == "assigned_to_id":
            if operator_raw in ("=", "!") and values:
                zammad_ids = [str(migration_map["users"].get(rid)) for rid in values if migration_map["users"].get(rid)]
                if zammad_ids:
                    condition["ticket.owner_id"] = {"operator": op_map[operator_raw], "value": zammad_ids}
            continue

        # --- tracker_id → group ---
        if field == "tracker_id":
            if operator_raw in ("=", "!") and values:
                gids = [
                    str(tracker_group_ids[f"tracker_{rid}"]) for rid in values if f"tracker_{rid}" in tracker_group_ids
                ]
                if gids:
                    condition["ticket.group_id"] = {"operator": op_map[operator_raw], "value": gids}
            continue

        # --- due_date ---
        # Redmine's "due_date !*" (no due date set) has no direct equivalent in Zammad
        # overview conditions — skip silently rather than emit an invalid condition.
        if field == "due_date":
            continue

        # --- cf_N (custom fields) ---
        if field.startswith("cf_"):
            zammad_name = cf_zammad_name.get(field)
            if not zammad_name:
                continue
            zammad_op = op_map.get(operator_raw)
            if zammad_op is None:
                continue
            if values:
                condition[f"ticket.{zammad_name}"] = {"operator": zammad_op, "value": values}
            continue

        # All other fields (child_id, project_id, etc.) are silently skipped.

    return condition


def _migrate_overviews(conn, api: _ZammadAPI, migration_map: dict, toml: dict, error_log: logging.Logger) -> None:
    queries = _read_redmine_queries(conn)
    print(f"\nMigrating {len(queries)} Redmine queries → Zammad overviews...")
    migrated = skipped = 0

    # Sort field mapping: Redmine field → Zammad order.by value (bare name, no ticket. prefix).
    sort_field_map = {
        "due_date": "pending_time",
        "updated_on": "updated_at",
        "created_on": "created_at",
        "priority": "priority_id",
        "status": "state_id",
        "id": "number",
        "subject": "title",
        "assigned_to": "owner_id",
    }
    # group_by mapping: Redmine field → Zammad bare field name (no ticket. prefix).
    group_by_map = {
        "status": "state_id",
        "priority": "priority_id",
        "assigned_to": "owner_id",
        "tracker": "group_id",
    }
    # Standard column set shown in overview tables (desktop / small / mobile views).
    default_view = {
        "d": ["title", "customer", "group", "created_at"],
        "s": ["title", "customer", "group", "created_at"],
        "m": ["number", "title", "customer", "group", "created_at"],
        "view_mode_default": "s",
    }
    # Role IDs: 1=Admin, 2=Agent (Zammad built-in, stable across instances).
    agent_role_ids = [1, 2]

    # Fetch all Zammad state IDs for use as an "all tickets" catch-all condition.
    # Zammad rejects overviews with empty or invalid conditions, so a query with no filters
    # (or filters that can't be mapped) needs an explicit "state is any of all states" condition.
    all_state_ids = [str(s["id"]) for s in api.get("ticket_states")]

    migration_map.setdefault("overviews", {})

    for query in queries:
        redmine_id = str(query["id"])
        if redmine_id in migration_map["overviews"]:
            skipped += 1
            continue

        condition = _parse_redmine_filters(query["filters"], migration_map, toml, error_log, query["name"])

        # Build sort order from first sort_criteria entry.
        import yaml as _yaml

        order: dict = {"by": "created_at", "direction": "ASC"}
        sort_raw = query["sort_criteria"]
        if sort_raw and sort_raw.strip() not in ("---", ""):
            try:
                sort_list = _yaml.safe_load(sort_raw) or []
                if sort_list and isinstance(sort_list[0], list) and len(sort_list[0]) == 2:  # noqa: PLR2004
                    field, direction = sort_list[0]
                    zammad_field = sort_field_map.get(str(field))
                    if zammad_field:
                        order = {"by": zammad_field, "direction": str(direction).upper()}
            except Exception:  # noqa: S110
                pass

        # group_by (bare field name, no ticket. prefix)
        group_by: str | None = None
        if query["group_by"]:
            group_by = group_by_map.get(str(query["group_by"]))

        overview_data: dict = {
            "name": query["name"],
            "condition": condition or {"ticket.state_id": {"operator": "is", "value": all_state_ids}},
            "order": order,
            "view": default_view,
            "active": True,
            "role_ids": agent_role_ids,
        }
        if group_by:
            overview_data["group_by"] = group_by

        try:
            result = api.post("overviews", overview_data)
        except _ZammadAPIError:
            # Already exists — find by name.
            all_overviews = api.search("overviews")
            match = next((o for o in all_overviews if o.get("name") == query["name"]), None)
            if not match:
                error_log.error(f"Overview '{query['name']}': creation failed and not found by name")
                continue
            result = match
        except Exception as e:
            error_log.error(f"Overview '{query['name']}': {e}")
            continue

        migration_map["overviews"][redmine_id] = result["id"]
        migrated += 1

    print(f"  Overviews: {migrated} migrated, {skipped} skipped")
    _save_migration_map(migration_map, api.dry_run)


def _run_migration(conn, api: _ZammadAPI, migration_map: dict, toml: dict, error_log: logging.Logger) -> None:
    """Run all migration steps in order."""
    # Tags can come from a plugin table or from a list-type custom field (name configured in TOML).
    tags_cf_name: str = toml.get("tags_custom_field", "")
    tags_table = _tags_table_exists(conn)
    tags_cf_id = _find_tags_custom_field_id(conn, tags_cf_name) if tags_cf_name else None
    if tags_table:
        print(f"\nTags table detected: '{tags_table}' — tags will be imported.")
        tags_by_issue = _read_redmine_tags_bulk(conn, tags_table)
    elif tags_cf_id is not None:
        print(f"\nTags custom field detected (id={tags_cf_id}) — tags will be imported as native Zammad tags.")
        tags_by_issue = _read_tags_from_custom_field(conn, tags_cf_id)
    else:
        print("\nNo tags source found — skipping tag import.")
        tags_by_issue = {}

    _migrate_states(conn, api, migration_map, toml, error_log)
    _migrate_custom_fields(conn, api, migration_map, error_log, skip_cf_id=tags_cf_id)
    _migrate_users(conn, api, migration_map, error_log)
    _migrate_group(conn, api, migration_map, toml, error_log)
    _migrate_tickets(
        conn, api, migration_map, toml, tags_by_issue, error_log, tags_cf_id=tags_cf_id, tags_cf_name=tags_cf_name
    )
    _migrate_articles(conn, api, migration_map, error_log)
    _migrate_links(conn, api, migration_map, error_log)
    _migrate_overviews(conn, api, migration_map, toml, error_log)


# --- Migration task ---


@task(
    help={
        "redmine_db_host": "Redmine PostgreSQL host",
        "redmine_db_port": "Redmine PostgreSQL port",
        "redmine_db_name": "Redmine database name",
        "redmine_db_user": "Redmine database user",
        "redmine_db_pass": "Redmine database password (or POSTGRES_PASSWORD env var)",
        "zammad_url": "Zammad base URL (or ZAMMAD_URL env var)",
        "zammad_token": "Zammad admin API token (or ZAMMAD_TOKEN env var)",
    }
)
def zammad_migrate(
    c: Context,
    redmine_db_host: str = "localhost",
    redmine_db_port: int = 5433,
    redmine_db_name: str = "redmine_migration",
    redmine_db_user: str = "postgres",
    redmine_db_pass: str = "",
    zammad_url: str = "",
    zammad_token: str = "",
) -> None:
    """Migrate Redmine issues to Zammad tickets via REST API.

    Import mode is enabled/disabled automatically. After migration, run:
        invoke zammad-reindex
    """
    dry_run: bool = c.config.run.dry

    if not redmine_db_pass:
        redmine_db_pass = os.environ.get("POSTGRES_PASSWORD", "")
    if not zammad_url:
        zammad_url = os.environ.get("ZAMMAD_URL", "http://localhost:8008")
    if not zammad_token:
        zammad_token = os.environ.get("ZAMMAD_TOKEN", "")

    if not redmine_db_pass:
        print_error("Redmine DB password required: --redmine-db-pass or POSTGRES_PASSWORD env var")
        raise Exit(code=1)
    if not zammad_token:
        print_error("Zammad token required: --zammad-token or ZAMMAD_TOKEN env var")
        raise Exit(code=1)

    try:
        toml = _load_toml()
    except FileNotFoundError as e:
        print_error(str(e))
        raise Exit(code=1) from e

    print("=" * 60)
    print("Redmine → Zammad Migration")
    print("=" * 60)
    if dry_run:
        print("\n⚠  DRY-RUN MODE — no changes will be made\n")

    error_log, error_counter = _setup_error_logging()
    migration_map = _load_migration_map()
    api = _ZammadAPI(zammad_url, zammad_token, dry_run=dry_run)

    print(f"Connecting to Redmine DB at {redmine_db_host}:{redmine_db_port}/{redmine_db_name}...")
    conn = _connect_redmine_db(redmine_db_host, redmine_db_port, redmine_db_name, redmine_db_user, redmine_db_pass)

    if not dry_run:
        _import_mode_on(c)

    try:
        _run_migration(conn, api, migration_map, toml, error_log)
    finally:
        conn.close()
        if not dry_run:
            _import_mode_off(c)

    error_count = error_counter.count
    print("\n" + "=" * 60)
    print("Migration complete!")
    print(f"  Map file:  {MAP_FILE}")
    print(f"  Error log: {ERROR_LOG}")
    print(f"\n  States:        {len(migration_map['states'])}")
    print(f"  Users:         {len(migration_map['users'])}")
    print(f"  Groups:        {len(migration_map['groups'])}")
    print(f"  Tickets:       {len(migration_map['tickets'])}")
    print(f"  Articles:      {len(migration_map['articles'])}")
    print(f"  Links:         {len(migration_map.get('links', {}))}")
    print(f"  Custom fields: {len(migration_map['custom_fields'])}")
    print(f"  Overviews:     {len(migration_map.get('overviews', {}))}")
    print(f"  Tags:          {len(migration_map.get('tags', {}))}")
    if error_count:
        print_error(f"  Errors:        {error_count} (see {ERROR_LOG})")
    else:
        print("  Errors:        0 ✅")
    print("=" * 60)
