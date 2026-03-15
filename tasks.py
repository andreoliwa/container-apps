"""Invoke tasks for containers."""

import os
import platform
import time
from pathlib import Path

from conjuring.grimoire import print_error
from invoke import Context, Exit, task
from postgres.tasks import db_connect, db_dump, db_list, db_restore  # noqa: F401
from zammad.tasks import (  # noqa: F401
    zammad_down,
    zammad_migrate,
    zammad_reindex,
    zammad_setup,
    zammad_up,
    zammad_wipe,
)


@task
def up_logs(c: Context, app: str) -> None:
    """Start a container app in the background and follow the logs."""
    command = f"docker compose -f ~/container-apps/{app}/docker-compose.yml"
    c.run(f"{command} up -d && {command} logs -f")


@task(
    help={
        "database": "Set up PostgreSQL database and data directories",
        "plugin": "Install tt-rss-plugin-vf-scored plugin into running container",
    }
)
def rss_setup(c: Context, database: bool = False, plugin: bool = False) -> None:
    """Set up TT-RSS: create database/directories (--database) or install plugin (--plugin)."""
    if not database and not plugin:
        print_error("At least one flag is required: --database or --plugin")
        print("\nUsage:")
        print("  invoke rss-setup --database         # Set up database and directories")
        print("  invoke rss-setup --plugin           # Install vf_scored plugin")
        print("  invoke rss-setup --database --plugin # Do both")
        raise Exit(code=1)

    if database:
        _setup_database(c)

    if plugin:
        _install_plugin(c)


def _setup_database(c: Context) -> None:
    """Set up PostgreSQL 17 database and data directories for TT-RSS."""
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
    c.run(f'docker exec postgres17 psql -U postgres -c "CREATE DATABASE {db_name};"')
    c.run(f"docker exec postgres17 psql -U postgres -c \"CREATE USER {db_user} WITH PASSWORD '{db_pass}';\"")
    c.run(f'docker exec postgres17 psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"')
    c.run(f'docker exec postgres17 psql -U postgres -d {db_name} -c "GRANT ALL ON SCHEMA public TO {db_user};"')

    print("\nStep 3: Creating data directories...")
    ttrss_dirs = data_dir_path / "ttrss"
    for subdir in ["data", "config", "redis"]:
        dir_path = ttrss_dirs / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {dir_path}")

    print("\n✅ TT-RSS database setup complete!")
    print("\nNext steps:")
    print("  1. invoke rss-up")
    print("  2. Open http://localhost:8002/tt-rss")
    print("  3. Login with admin credentials and enable plugins in Preferences.")


def _install_plugin(c: Context) -> None:
    """Install tt-rss-plugin-vf-scored plugin into running TT-RSS container."""
    container_name = "ttrss-app"
    plugin_url = "https://github.com/andreoliwa/tt-rss-plugin-vf-scored.git"
    plugin_dir = "/var/www/html/tt-rss/plugins.local"
    plugin_name = "vf_scored"

    print(f"Step 1: Checking if {container_name} container is running...")
    result = c.run(f"docker ps --filter name={container_name} --format '{{{{.Names}}}}'", hide=True, warn=True)

    if not result or container_name not in result.stdout:
        print_error(f"Container '{container_name}' is not running!")
        print("\nPlease start the RSS stack first:")
        print("  invoke rss-up")
        raise Exit(code=1)

    print(f"✓ Container {container_name} is running")

    print("\nStep 2: Checking if plugin is already installed...")
    check_result = c.run(
        f"docker exec {container_name} test -d {plugin_dir}/{plugin_name} && echo 'exists' || echo 'not found'",
        hide=True,
        warn=True,
    )

    if "exists" in check_result.stdout:
        print(f"⚠ Plugin already installed at {plugin_dir}/{plugin_name}")
        print("\nTo reinstall, remove it first:")
        print(f"  docker exec {container_name} rm -rf {plugin_dir}/{plugin_name}")
        return

    print(f"\nStep 3: Installing plugin from {plugin_url}...")
    c.run(f"docker exec {container_name} git clone {plugin_url} {plugin_dir}/{plugin_name}")

    print("\n✅ Plugin installation complete!")
    print("\nNext steps:")
    print("  1. Open http://localhost:8002/tt-rss")
    print("  2. Go to Preferences → Plugins")
    print(f"  3. Enable '{plugin_name}' plugin")
    print("  4. Configure your keyword scoring rules")


@task
def setup_grav(c: Context) -> None:
    """Set up Grav CMS: create data directory, start container, install themes and plugins."""
    data_dir = os.environ.get("CONTAINER_APPS_DATA_DIR")

    if not data_dir:
        print_error("CONTAINER_APPS_DATA_DIR environment variable is required")
        raise Exit(code=1)

    data_dir_path = Path(data_dir).expanduser()

    print("Step 1: Creating data directory...")
    grav_dir = data_dir_path / "grav"
    grav_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {grav_dir}")

    print("\nStep 2: Starting Grav container...")
    c.run("cd grav && docker compose up -d")

    print("\nStep 3: Waiting for Grav to initialize (15 seconds)...")
    time.sleep(15)

    print("\nStep 4: Installing themes...")
    themes = ["quark", "lingonberry", "future2021", "future"]
    for theme in themes:
        print(f"  Installing theme: {theme}")
        c.run(f"docker exec -w /app/www/public grav bin/gpm install {theme} -y", warn=True)

    print("\nStep 5: Installing Instagram plugin...")
    c.run("docker exec -w /app/www/public grav bin/gpm install instagram -y", warn=True)

    print("\n✅ Grav CMS setup complete!")
    print("\nNext steps:")
    print("  1. Open http://localhost:8007/admin")
    print("  2. Create your admin account (first user becomes admin)")
    print("  3. Configure your site and start creating content!")
    print("\nInstalled themes: Quark, Lingonberry, Future2021, Future")
    print("Installed plugins: Admin (pre-installed), Instagram")


def _docker_compose_rss(c: Context, dev: bool, command: str, follow_logs: bool = False) -> None:
    """Run docker compose with the appropriate compose files.

    Args:
        c: Invoke context
        dev: If True, use dev mode with compose.override.dev.yaml
        command: Docker compose command to run (e.g., "up -d", "down", "pull")
        follow_logs: If True and command contains "up -d", follow logs after starting

    """
    # Get the container apps directory from environment or use default
    container_apps_dir = os.environ.get("CONTAINER_APPS_DIR", "~/container-apps")
    container_apps_path = Path(container_apps_dir).expanduser()

    compose_files = f"-f {container_apps_path}/rss/compose.yaml"
    if dev:
        compose_files += f" -f {container_apps_path}/rss/compose.override.dev.yaml"

    c.run(f"docker compose {compose_files} {command}")

    if follow_logs and "up -d" in command:
        c.run(f"docker compose {compose_files} logs -f")


@task(
    help={
        "pull": "Update stack before starting (pull images in normal mode, or sync fork + build in dev mode)",
        "dev": "Use dev mode (local tt-rss clone with vf_scored plugin)",
    }
)
def rss_up(c: Context, pull: bool = False, dev: bool = False) -> None:
    """Start the TT-RSS stack."""
    ttrss_repo_dir = os.environ.get("TTRSS_REPO_DIR")

    if pull:
        if dev:
            # Dev mode: sync fork, pull, build
            if not ttrss_repo_dir:
                print_error("TTRSS_REPO_DIR environment variable is required for dev mode")
                raise Exit(code=1)

            print("Dev mode: Syncing fork, pulling, and building...")
            if platform.system() != "Darwin":
                print("Changing owner and permissions on Linux...")
                c.run(f"chown -R root:root {ttrss_repo_dir}")
                c.run(f"chmod 777 {ttrss_repo_dir}")
            c.run(f"pushd {ttrss_repo_dir} && invoke fork.sync && popd")
            _docker_compose_rss(c, dev=True, command="down")
            _docker_compose_rss(c, dev=True, command="pull")
            _docker_compose_rss(c, dev=True, command="build")
        else:
            # Normal mode: pull images
            print("Normal mode: Pulling latest images...")
            _docker_compose_rss(c, dev=False, command="down")
            _docker_compose_rss(c, dev=False, command="pull")

    # Start and follow logs
    mode_name = "dev" if dev else "normal"
    print(f"Starting TT-RSS stack in {mode_name} mode...")
    _docker_compose_rss(c, dev=dev, command="up -d", follow_logs=True)


def _detect_rss_dev_mode(c: Context) -> bool:
    """Auto-detect if RSS stack is running in dev mode.

    Detection strategy (in order of reliability):
    1. Check SKIP_RSYNC_ON_STARTUP environment variable (dev-specific)
    2. Check for bind mount vs named volume
    3. Default to normal mode if container not running
    """
    # Check if container exists and is running
    check = c.run("docker ps -a --filter name=ttrss-app --format '{{.Names}}'", hide=True, warn=True)

    if not check or "ttrss-app" not in check.stdout:
        print("⚠ RSS stack containers not found, assuming normal mode")
        return False

    # Primary detection: check for dev-specific env var
    env_check = c.run(
        "docker inspect ttrss-app --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -q SKIP_RSYNC_ON_STARTUP",
        hide=True,
        warn=True,
    )

    if env_check and env_check.ok:
        return True

    # Fallback: check mount type
    mount_check = c.run(
        "docker inspect ttrss-app --format"
        " '{{range .Mounts}}{{if eq .Destination \"/var/www/html/tt-rss\"}}{{.Type}}{{end}}{{end}}'",
        hide=True,
        warn=True,
    )

    return mount_check and "bind" in mount_check.stdout


@task
def rss_down(c: Context) -> None:
    """Stop the TT-RSS stack (auto-detects dev/normal mode)."""
    dev = _detect_rss_dev_mode(c)
    mode_name = "dev" if dev else "normal"
    print(f"Detected {mode_name} mode, stopping TT-RSS stack...")
    _docker_compose_rss(c, dev=dev, command="down")


@task
def rss_logs(c: Context) -> None:
    """Follow TT-RSS stack logs (auto-detects dev/normal mode)."""
    dev = _detect_rss_dev_mode(c)
    _docker_compose_rss(c, dev=dev, command="logs -f")
