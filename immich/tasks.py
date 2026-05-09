"""Invoke tasks for Immich photo and video management."""

import os
import socket
from datetime import UTC, datetime
from pathlib import Path

from conjuring.grimoire import lazy_env_variable, print_error
from invoke import Context, Exit, task

IMMICH_CONTAINER = "immich-db"
IMMICH_DB_USER = "immich"
IMMICH_DB_NAME = "immich"

IMMICH_DIR = Path(__file__).parent


def _compose_file(_c: Context) -> str:
    container_apps_dir = os.environ.get("CONTAINER_APPS_DIR", "~/container-apps")
    return f"-f {Path(container_apps_dir).expanduser()}/immich/compose.yaml"


@task
def immich_setup(c: Context) -> None:
    """Set up Immich: ensure env vars are set and create the library data directory.

    The Postgres database and user are created automatically by the bundled
    immich-db container on first start (via POSTGRES_USER/PASSWORD/DB env vars).
    """
    # Validate required env var before starting anything — fail fast.
    lazy_env_variable("IMMICH_DB_PASSWORD", "Immich PostgreSQL password")

    data_dir = os.environ.get("CONTAINER_APPS_DATA_DIR")
    if not data_dir:
        print_error("CONTAINER_APPS_DATA_DIR environment variable is required")
        raise Exit(code=1)

    print("Step 1: Ensuring redis is running...")
    c.run("cd ~/container-apps/redis && docker compose up -d")

    print("\nStep 2: Creating library data directory...")
    library_dir = Path(data_dir).expanduser() / "immich" / "library"
    library_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {library_dir}")

    print("\n✅ Immich setup complete!")
    print("\nNext steps:")
    print("  invoke immich-up")
    print("  Open http://localhost:2283 and create admin account")


@task(help={"pull": "Pull latest Immich image before starting"})
def immich_up(c: Context, pull: bool = False) -> None:
    """Start Redis, then the Immich stack (immich-db starts automatically)."""
    c.run("ca redis up")

    cf = _compose_file(c)

    if pull:
        print("Pulling latest Immich images...")
        c.run(f"docker compose {cf} pull")

    print("Starting Immich stack...")
    c.run(f"docker compose {cf} up -d")
    c.run(f"docker compose {cf} logs -f", warn=True, pty=True)


@task(help={"output_dir": "Output directory (default: $BACKUP_DIR/<hostname>/immich)"})
def immich_dump(c: Context, output_dir: str = "") -> None:
    """Dump the Immich database with a timestamp in the file name."""
    datetime_str = datetime.now(UTC).isoformat().replace(":", "-").split(".")[0]

    if output_dir:
        output_path = Path(output_dir).expanduser()
    else:
        host_name = socket.gethostname().replace(".local", "")
        output_path = Path(lazy_env_variable("BACKUP_DIR", "Backup directory")).expanduser() / host_name / "immich"

    output_path.mkdir(parents=True, exist_ok=True)

    full_dump_path = output_path / f"{IMMICH_DB_NAME}_{datetime_str}.sql"
    c.run(f"docker exec {IMMICH_CONTAINER} pg_dump -U {IMMICH_DB_USER} {IMMICH_DB_NAME} > {full_dump_path}")
    c.run(f"ls -lrth {output_path!s} | tail -n 20", dry=False)


@task
def browse(c: Context) -> None:
    """Browse Immich library."""
    c.run("open http://localhost:2283")
