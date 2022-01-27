"""Invoke tasks for containers."""
from invoke import task, Exit
from datetime import datetime
from pathlib import Path
import os
import socket
from conjuring.grimoire import print_error, run_command

DB_USER = "postgres"
POSTGRES_VERSION = 14
POSTGRES_ENV = "POSTGRES_PASSWORD"
DB_PASSWORD = os.environ.get(POSTGRES_ENV)
BACKUP_PATH = Path("~/OneDrive/Backup").expanduser()


@task(
    help={
        "database": "Database name",
        "version": f"PostgreSQL version (default: {POSTGRES_VERSION})",
        "psql": "Use psql instead of pgcli",
        "command": "Run a SQL command (only works with psql, ignored on pgcli)",
        "user": f"User name (default: {DB_USER})",
        "password_env": f"Environment variable with the password (default: {POSTGRES_ENV})",
    }
)
def db_connect(c, database="postgres", version=POSTGRES_VERSION, psql=False, command="", user="", password_env=""):
    """Connect to the containerised PostgreSQL database using pgcli."""
    db_user = user or DB_USER
    db_password = os.environ[password_env.upper()] if password_env else DB_PASSWORD
    if psql:
        run_command(
            c,
            f"docker exec -it postgres{version} psql -U {db_user}",
            f'--command="{command}"' if command else "",
            database,
        )
    else:
        if command:
            print_error(f"Use --psql to run this command: {command}")
            raise Exit(code=1)

        port = f"77{version}"
        c.run(f"pgcli postgresql://{db_user}:{db_password}@localhost:{port}/{database}")


@task(
    help={
        "database": "Database name",
        "version": f"PostgreSQL version (default: {POSTGRES_VERSION})",
        "output_dir": f"Output directory for the dump file (default: {str(BACKUP_PATH)})",
    }
)
def db_dump(c, database, version=POSTGRES_VERSION, output_dir=""):
    """Dump a single database (with date/time on the file name)."""
    datetime_str = datetime.now().isoformat().replace(":", "-").split(".")[0]

    if not output_dir:
        host_name = socket.gethostname().replace(".local", "")
        output_dir = BACKUP_PATH / host_name / f"postgres{version}"

    expanded_dir = Path(output_dir).expanduser()
    expanded_dir.mkdir(exist_ok=True, parents=True)

    full_dump_path = expanded_dir / f"{database}_{datetime_str}.sql"
    c.run(f"docker exec -it postgres{version} pg_dump -U postgres {database} > {full_dump_path}")
    c.run(f"ls -l {str(expanded_dir)}")


@task
def up_logs(c, app):
    """Start a container app in the background and follow the logs."""
    command = f"docker compose -f ~/container-apps/{app}/docker-compose.yml"
    c.run(f"{command} up -d && {command} logs -f")
