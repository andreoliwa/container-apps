"""Invoke tasks for containers."""

import os
import socket
from datetime import UTC, datetime
from pathlib import Path

from conjuring.grimoire import print_error, run_command
from invoke import Context, Exit, task

DB_USER = "postgres"
POSTGRES_VERSION = 14
POSTGRES_ENV = "POSTGRES_PASSWORD"
BACKUP_PATH = Path("~/OneDrive/Backup").expanduser()


@task(
    help={
        "database": "Database name",
        "version": f"PostgreSQL version (default: {POSTGRES_VERSION})",
        "psql": "Use psql instead of pgcli",
        "command": "Run a SQL command (only works with psql, ignored on pgcli)",
    }
)
def db_connect(
    c: Context,
    database: str = "postgres",
    version: int = POSTGRES_VERSION,
    psql: bool = False,
    command: str = "",
) -> None:
    """Connect to the containerised PostgreSQL database using pgcli."""
    db_user = DB_USER
    db_password = os.environ[POSTGRES_ENV.upper()]
    if psql:
        run_command(
            c,
            f"docker exec -it postgres{version} psql -U {db_user} --csv --tuples-only",
            f'--command="{command}"' if command else "",
            database,
        )
    else:
        if command:
            print_error(f"Use --psql to run this command: {command}")
            raise Exit(code=1)

        port = f"77{version}"
        # List databases fails on pgcli; I tried --list before and after the connection string:
        #   connection is bad: No such file or directory
        #   Is the server running locally and accepting connections on that socket?
        c.run(f"pgcli postgresql://{db_user}:{db_password}@localhost:{port}/{database}")


@task(
    help={
        "version": f"PostgreSQL version (default: {POSTGRES_VERSION})",
    }
)
def db_list(c: Context, version: int = POSTGRES_VERSION) -> None:
    """List databases using psql."""
    db_user = DB_USER
    command = (
        "SELECT datname AS database_name FROM pg_database"
        " WHERE datname NOT IN ('postgres') AND datname NOT LIKE 'template%';"
    )
    run_command(
        c,
        f"docker exec -it postgres{version} psql -U {db_user} --csv --tuples-only",
        f'--command="{command}"',
        "postgres",
    )


@task(
    help={
        "database": "Database name",
        "version": f"PostgreSQL version (default: {POSTGRES_VERSION})",
        "output_dir": f"Output directory for the dump file (default: {BACKUP_PATH!s})",
    }
)
def db_dump(c: Context, database: str, version: int = POSTGRES_VERSION, output_dir: str = "") -> None:
    """Dump a single database (with date/time on the file name)."""
    datetime_str = datetime.now(UTC).isoformat().replace(":", "-").split(".")[0]

    output_path: Path
    if not output_dir:
        host_name = socket.gethostname().replace(".local", "")
        output_path = BACKUP_PATH / host_name / f"postgres{version}"
    else:
        output_path = Path(output_dir).expanduser()

    output_path.mkdir(exist_ok=True, parents=True)

    full_dump_path = output_path / f"{database}_{datetime_str}.sql"
    c.run(f"docker exec -it postgres{version} pg_dump -U postgres {database} > {full_dump_path}")
    c.run(f"ls -lrth {output_path!s} | tail -n 20", dry=False)


@task
def up_logs(c: Context, app: str) -> None:
    """Start a container app in the background and follow the logs."""
    command = f"docker compose -f ~/container-apps/{app}/docker-compose.yml"
    c.run(f"{command} up -d && {command} logs -f")


@task
def setup_ttrss(c: Context) -> None:
    """Set up TT-RSS: start PostgreSQL 17, create database, create data directories."""
    db_name = os.environ.get("TTRSS_DB_NAME", "ttrss")
    db_user = os.environ.get("TTRSS_DB_USER", "ttrss")
    db_pass = os.environ.get("TTRSS_DB_PASS")
    data_dir = os.environ.get("CONTAINER_APPS_DATA_DIR")

    if not db_pass:
        print_error("TTRSS_DB_PASS environment variable is required")
        raise Exit(code=1)

    if not data_dir:
        print_error("CONTAINER_APPS_DATA_DIR environment variable is required")
        raise Exit(code=1)

    data_dir_path = Path(data_dir).expanduser()

    print("Step 1: Starting PostgreSQL 17...")
    c.run("cd postgres && docker compose up -d postgres17")

    print("\nStep 2: Creating TT-RSS database and user...")
    c.run(f'docker exec -it postgres17 psql -U postgres -c "CREATE DATABASE {db_name};"')
    c.run(f"docker exec -it postgres17 psql -U postgres -c \"CREATE USER {db_user} WITH PASSWORD '{db_pass}';\"")
    c.run(f'docker exec -it postgres17 psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"')
    c.run(f'docker exec -it postgres17 psql -U postgres -d {db_name} -c "GRANT ALL ON SCHEMA public TO {db_user};"')

    print("\nStep 3: Creating data directories...")
    ttrss_dirs = data_dir_path / "ttrss"
    for subdir in ["data", "config", "redis"]:
        dir_path = ttrss_dirs / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {dir_path}")

    print("\n✅ TT-RSS setup complete!")
    print("\nNext steps:")
    print("  1. cd rss && docker compose up -d")
    print("  2. Open http://localhost:8002/")
    print("  3. Login with user 'admin', password 'password' and change it immediately.")
