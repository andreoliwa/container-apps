"""Invoke tasks for Grav CMS."""

import os
import time
from pathlib import Path

from conjuring.grimoire import print_error, print_normal
from invoke import Context, Exit, task


def _dry(c: Context) -> bool:
    return bool(c.config.run.dry)


@task
def grav_setup(c: Context) -> None:
    """Set up Grav CMS: create data directory, start container, install themes and plugins."""
    data_dir = os.environ.get("CONTAINER_APPS_DATA_DIR")

    if not data_dir:
        print_error("CONTAINER_APPS_DATA_DIR environment variable is required")
        raise Exit(code=1)

    dry = _dry(c)
    data_dir_path = Path(data_dir).expanduser()

    print_normal("Step 1: Creating data directory...", dry=dry)
    grav_dir = data_dir_path / "grav"
    grav_dir.mkdir(parents=True, exist_ok=True)
    print_normal(f"  Created: {grav_dir}", dry=dry)

    print_normal("\nStep 2: Starting Grav container...", dry=dry)
    c.run("docker compose up -d")

    print_normal("\nStep 3: Waiting for Grav to initialize (15 seconds)...", dry=dry)
    time.sleep(15)

    print_normal("\nStep 4: Installing themes...", dry=dry)
    themes = ["quark", "lingonberry", "future2021", "future"]
    for theme in themes:
        print_normal(f"  Installing theme: {theme}", dry=dry)
        c.run(f"docker exec -w /app/www/public grav bin/gpm install {theme} -y", warn=True)

    print_normal("\nStep 5: Installing Instagram plugin...", dry=dry)
    c.run("docker exec -w /app/www/public grav bin/gpm install instagram -y", warn=True)

    print_normal("\nGrav CMS setup complete!", dry=dry)
    print_normal("\nNext steps:", dry=dry)
    print_normal("  1. Open http://localhost:8007/admin", dry=dry)
    print_normal("  2. Create your admin account (first user becomes admin)", dry=dry)
    print_normal("  3. Configure your site and start creating content!", dry=dry)
    print_normal("\nInstalled themes: Quark, Lingonberry, Future2021, Future", dry=dry)
    print_normal("Installed plugins: Admin (pre-installed), Instagram", dry=dry)
