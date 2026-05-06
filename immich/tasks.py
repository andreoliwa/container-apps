"""Invoke tasks for Immich photo and video management."""

import os
from pathlib import Path

from conjuring.grimoire import lazy_env_variable, print_error
from invoke import Context, Exit, task

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
    """Start the Immich stack (requires redis running; immich-db starts automatically)."""
    cf = _compose_file(c)

    if pull:
        print("Pulling latest Immich images...")
        c.run(f"docker compose {cf} pull")

    print("Starting Immich stack...")
    c.run(f"docker compose {cf} up -d")
    c.run(f"docker compose {cf} logs -f")


@task
def immich_down(c: Context) -> None:
    """Stop the Immich stack."""
    cf = _compose_file(c)
    print("Stopping Immich stack...")
    c.run(f"docker compose {cf} down")
