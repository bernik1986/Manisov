"""Release preflight, narrowly scoped data ownership, and safe restore extraction."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
from urllib.parse import unquote, urlsplit


def validate_config(config):
    services = config["services"]
    env = services["backend"]["environment"]
    db = services["db"]["environment"]
    url = urlsplit(env["DATABASE_URL"])
    expected = (db["POSTGRES_USER"], db["POSTGRES_PASSWORD"], db["POSTGRES_DB"])
    actual = (unquote(url.username or ""), unquote(url.password or ""), unquote(url.path.lstrip("/")))
    if url.scheme != "postgresql+psycopg2" or url.hostname != "db" or url.port not in (None, 5432) or actual != expected or url.query:
        raise ValueError("DATABASE_URL must target this Compose db and match POSTGRES_* exactly")
    if len(env.get("JWT_SECRET_KEY", "")) < 32 or env["JWT_SECRET_KEY"].startswith("change-"):
        raise ValueError("A unique JWT secret of at least 32 characters is required")
    if not env.get("DEFAULT_ADMIN_USERNAME") or len(env.get("DEFAULT_ADMIN_PASSWORD", "")) < 8 or env["DEFAULT_ADMIN_PASSWORD"] in {"admin123", "admin12345"} or env["DEFAULT_ADMIN_PASSWORD"].startswith("change-"):
        raise ValueError("Explicit non-default bootstrap credentials required")
    if env["MANISOV_ENV"] != "production" or str(env["AUTO_ALEMBIC_ON_STARTUP"]) != "0":
        raise ValueError("Production must use explicit deploy-time migrations")
    volumes = services["backend"]["volumes"]
    if {v["target"] for v in volumes} != {"/app/uploads", "/app/templates", "/app/generated"}:
        raise ValueError("Only data directories may be mounted in the backend")
    for volume in volumes:
        source = Path(volume["source"])
        if not source.is_absolute() or not source.is_dir() or source.is_symlink():
            raise ValueError(f"Provision existing real data directory first: {source}")
    return config


def container_environment(info):
    return dict(entry.split("=", 1) for entry in info["Config"].get("Env", []) if "=" in entry)


def validate_database(config, container_id, backend_id=""):
    info = json.loads(subprocess.check_output(["docker", "inspect", container_id]))[0]
    expected = config["volumes"]["postgres_data"]["name"]
    mounts = [m for m in info["Mounts"] if m["Destination"] == "/var/lib/postgresql/data"]
    if len(mounts) != 1 or mounts[0].get("Name") != expected:
        raise ValueError("Existing database volume does not match POSTGRES_VOLUME; refusing deployment")
    if info["Config"]["Labels"].get("com.docker.compose.project") != config["name"]:
        raise ValueError("Existing database has a different Compose project")
    actual_env = container_environment(info)
    expected_env = config["services"]["db"]["environment"]
    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        if actual_env.get(key) != expected_env[key]:
            raise ValueError(f"Existing database {key} differs; plan DB configuration changes separately")
    if backend_id:
        backend = json.loads(subprocess.check_output(["docker", "inspect", backend_id]))[0]
        if backend["Config"]["Labels"].get("com.docker.compose.project") != config["name"]:
            raise ValueError("Existing backend has a different Compose project")
        if container_environment(backend).get("DATABASE_URL") != config["services"]["backend"]["environment"]["DATABASE_URL"]:
            raise ValueError("Existing backend DATABASE_URL differs; refusing to back up a different database")
        for volume in config["services"]["backend"]["volumes"]:
            existing = [m for m in backend["Mounts"] if m["Destination"] == volume["target"]]
            if len(existing) != 1 or existing[0]["Type"] != "bind" or Path(existing[0]["Source"]).resolve() != Path(volume["source"]).resolve():
                raise ValueError(f"Existing backend data bind differs at {volume['target']}; migrate data separately")


def prepare_data(root=Path("/app")):
    paths = []
    for name in ("uploads", "templates", "generated"):
        base = root / name
        if not base.is_dir() or base.is_symlink():
            raise ValueError(f"Not a real data directory: {base}")
        paths.append(base)
        for parent, dirs, files in os.walk(base, followlinks=False):
            paths.extend(Path(parent) / child for child in dirs + files)
    # Validate the whole tree before altering ownership; never follow user links.
    for path in paths:
        mode = path.lstat().st_mode
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError(f"Unsupported data entry: {path}")
    for path in paths:
        os.chown(path, 10001, 10001, follow_symlinks=False)
        os.chmod(path, 0o750 if path.is_dir() else 0o640, follow_symlinks=False)


def extract_files(archive, destination):
    destination = Path(destination)
    if not destination.is_dir() or destination.is_symlink() or any(destination.iterdir()):
        raise ValueError("Restore destination must be a new empty real directory")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in {"uploads", "templates"}:
                raise ValueError("Unsafe backup member path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("Links and special files are not restored")
        tar.extractall(destination, members=members, filter="data")


if __name__ == "__main__":
    action = sys.argv[1]
    if action in {"config", "database"}:
        config = validate_config(json.load(sys.stdin))
        if action == "database":
            validate_database(config, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    elif action == "prepare":
        prepare_data()
    elif action == "extract":
        extract_files(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("Unknown deployment data action")
