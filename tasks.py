"""Invoke tasks for containers."""
from invoke import task, Exit
from datetime import datetime
from pathlib import Path
import os
from invoke_home import print_error, run_command

DB_USER = "postgres"
DB_PASSWORD = os.environ["POSTGRES_PASSWORD"]


@task(
    help={
        "database": "Database name",
        "version": "PostgreSQL version: 13 (default) or 12",
        "psql": "Use psql instead of pgcli",
        "command": "Run a SQL command (only works with psql, ignored on pgcli)",
    }
)
def db_connect(c, database="postgres", version=13, psql=False, command=""):
    """Connect to the containerised PostgreSQL database using pgcli."""
    if psql:
        run_command(
            c,
            f"docker exec -it postgres{version} psql -U {DB_USER}",
            f'--command="{command}"' if command else "",
            database,
        )
    else:
        if command:
            print_error(f"Use --psql to run this command: {command}")
            raise Exit(code=1)

        port = f"77{version}"
        c.run(f"pgcli postgresql://{DB_USER}:{DB_PASSWORD}@localhost:{port}/{database}")


@task(
    help={
        "database": "Database name",
        "version": "PostgreSQL version: 13 (default) or 12",
        "output_dir": "Output directory for the dump file",
    }
)
def db_dump(c, database, version=13, output_dir="~/Downloads"):
    """Dump a single database (with date/time on the file name)."""
    datetime_str = datetime.now().isoformat().replace(":", "-").split(".")[0]
    expanded_dir = Path(output_dir).expanduser()
    full_dump_path = expanded_dir / f"{database}_{datetime_str}.sql"
    c.run(f"docker exec -it postgres{version} pg_dump -U postgres {database} > {full_dump_path}")
    c.run(f"ls -l {str(expanded_dir)}")
