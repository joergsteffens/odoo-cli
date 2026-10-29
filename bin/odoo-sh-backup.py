#!/usr/bin/env python3
"""Mirror Odoo.sh's backup.daily directory to this host and repack the daily
backup as a single ZIP that can be restored directly (Database Manager,
/web/database/restore)."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_HOST = "bareos.odoo.com"
TARGET_DIR = Path("/var/lib/odoo-backup/odoo-daily-backup")
# Where to write the restorable ZIP (default: <TARGET_DIR>.zip).
ZIP_FILE = None  # Path or None

# Optional overrides. Leave empty to derive both from the database name that
# Odoo.sh exposes at https://<PROJECT_HOST>/web/database/list, e.g.
# "bareos-odoo-production-25995407" -> build id 25995407 (the SSH user).
DB = ""
BUILD_ID = ""

# Progress messages are only shown with --verbose.
VERBOSE = False

SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
    # Fail fast instead of waiting for the long TCP connect timeout.
    "-o",
    "ConnectTimeout=15",
]
JSONRPC_CALL = {"jsonrpc": "2.0", "method": "call", "params": {}}


def parse_args(argv=None) -> argparse.Namespace:
    """Parse command line arguments (defaults come from the constants)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print progress messages",
    )
    parser.add_argument(
        "--host",
        default=PROJECT_HOST,
        help="Odoo.sh project host (default: %(default)s)",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=TARGET_DIR,
        help="local mirror directory, dedicated to this backup (default: %(default)s)",
    )
    parser.add_argument(
        "--zip-file",
        type=Path,
        default=ZIP_FILE,
        help="where to write the restorable ZIP (default: <target-dir>.zip)",
    )
    parser.add_argument(
        "--db",
        default=DB,
        help="database name (default: discover via the database list endpoint)",
    )
    parser.add_argument(
        "--build-id",
        default=BUILD_ID,
        help="Odoo.sh build id / SSH user (default: derived from the database name)",
    )
    return parser.parse_args(argv)


def log(message: str) -> None:
    """Print a progress line when --verbose is set, flushed for log ordering."""
    if VERBOSE:
        print(message, flush=True)


def ensure_writable_dir(path: Path) -> None:
    """Create the directory if needed and fail early if it is not writable."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as e:
        raise RuntimeError(f"{path} is not writable: {e}") from e


def discover_db(host: str) -> str:
    """Return the production database name.

    The database name ends in the current build id, which is also the SSH
    user. Resolved without credentials through the public database list
    endpoint (fails if Odoo disables that endpoint on the project).
    """
    url = f"https://{host}/web/database/list"
    req = urllib.request.Request(
        url,
        data=json.dumps(JSONRPC_CALL).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    try:
        return data["result"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected response from {url}") from e


def resolve_db(host: str, db: str, build_id: str):
    """Return (database, build id), using the overrides when set."""
    if db and build_id:
        return db, build_id
    log("discovering database/build id ...")
    discovered = discover_db(host)
    return db or discovered, build_id or discovered.rsplit("-", 1)[-1]


def sync_backups(ssh_host: str, db: str, db_prefix: str, target_dir: Path) -> None:
    """Mirror the *_daily artifacts of the remote backup.daily directory.

    target_dir is dedicated to this mirror, so --delete-excluded also removes
    everything else in it (pre-update backups, files from previous build
    ids, ...).
    """
    # Refuse to mirror (and therefore delete) when the remote daily dump is
    # missing, e.g. during a botched deploy or with a stale build id.
    # ssh exits with 255 on its own errors (auth, connection), otherwise
    # with the remote command's exit status.
    log(f"checking {db}_daily.sql.gz on {ssh_host} ...")
    guard = subprocess.run(
        ["ssh", *SSH_OPTS, ssh_host, "test", "-f", f"backup.daily/{db}_daily.sql.gz"],
        check=False,
        stderr=subprocess.PIPE,
    )
    # Decode instead of subprocess text mode, which needs Python 3.7.
    stderr = guard.stderr.decode("utf-8", errors="replace").strip()
    if guard.returncode == 255:
        hint = ""
        if "Permission denied" in stderr:
            hint = " (check your SSH key on Odoo.sh: Profile -> Add a key manually)"
        raise RuntimeError(f"cannot connect to {ssh_host}: {stderr}{hint}")
    if guard.returncode != 0:
        raise RuntimeError(
            f"remote daily backup {db}_daily.sql.gz not found; not syncing"
        )
    log(f"syncing backup.daily from {ssh_host} to {target_dir} ...")
    subprocess.run(
        [
            "rsync",
            "-avh",
            "--partial",
            "--progress",
            "--delete",
            "--delete-excluded",
            f"--include=/{db_prefix}-*_daily*",
            f"--include=/{db_prefix}-*_daily*/**",
            "--exclude=*",
            "-e",
            " ".join(["ssh", *SSH_OPTS]),
            f"{ssh_host}:backup.daily/",
            f"{target_dir}/",
        ],
        check=True,
    )


def create_backup_zip(db: str, target_dir: Path, zip_file: Path) -> None:
    """Repack the synced daily backup into a single ZIP with the same layout
    as an Odoo.sh download (dump.sql + manifest.json + filestore/)."""
    log(f"creating backup zip {zip_file} ...")
    sql_gz = target_dir / f"{db}_daily.sql.gz"
    filestore_src = target_dir / f"{db}_daily" / "home/odoo/data/filestore" / db
    zip_tmp = zip_file.with_name(f"{zip_file.name}.tmp.{os.getpid()}")
    try:
        with zipfile.ZipFile(zip_tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            # dump.sql first, like Odoo's own ZIP backups. Nested because the
            # parenthesized multi-context form needs Python 3.10.
            with gzip.open(sql_gz, "rb") as src:  # noqa: SIM117
                with zf.open("dump.sql", mode="w", force_zip64=True) as dst:
                    shutil.copyfileobj(src, dst)
            manifest = {"odoo_dump": "1", "db_name": db}
            zf.writestr("manifest.json", json.dumps(manifest) + "\n")
            if filestore_src.is_dir():
                for path in sorted(filestore_src.rglob("*")):
                    if path.is_file():
                        zf.write(path, f"filestore/{path.relative_to(filestore_src)}")
        os.replace(zip_tmp, zip_file)
    except BaseException:
        try:
            zip_tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    print(f"backup zip: {zip_file}", flush=True)


def main(argv=None) -> None:
    global VERBOSE

    args = parse_args(argv)
    VERBOSE = args.verbose
    ensure_writable_dir(args.target_dir)

    db, build_id = resolve_db(args.host, args.db, args.build_id)
    log(f"database: {db}")
    ssh_host = f"{build_id}@{args.host}"
    # Without the trailing build id, so dailies of previous builds still
    # match the filters and get deleted locally after a redeploy.
    db_prefix = db.rsplit("-", 1)[0]

    sync_backups(ssh_host, db, db_prefix, args.target_dir)
    zip_file = args.zip_file or args.target_dir.parent / f"{args.target_dir.name}.zip"
    create_backup_zip(db, args.target_dir, zip_file)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as e:
        ts = datetime.now().astimezone().isoformat()
        print(f"odoo-sh-backup failed at {ts}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
