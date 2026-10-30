#!/usr/bin/env python3
"""Mirror Odoo.sh's backup.daily directory to this host and repack the daily
backup as a single ZIP that can be restored directly (Database Manager,
/web/database/restore)."""

import argparse
import fcntl
import gzip
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_HOST = "bareos.odoo.com"
TARGET_DIR = Path("/var/local/odoo-backup/odoo-daily-backup")
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

# Timeouts so an unattended run cannot block forever: the SSH guard is killed
# after SSH_TIMEOUT seconds, rsync aborts after RSYNC_TIMEOUT seconds without
# any I/O on the connection.
SSH_TIMEOUT = 60
RSYNC_TIMEOUT = 600

# Marker file identifying a directory as a mirror owned by this tool.
MIRROR_MARKER = ".odoo-sh-backup-mirror"

JSONRPC_CALL = {"jsonrpc": "2.0", "method": "call", "params": {}}

HOST_RE = re.compile(r"[A-Za-z0-9.-]+")
DB_RE = re.compile(r"[A-Za-z0-9_-]+")
BUILD_ID_RE = re.compile(r"[0-9]+")


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
        "--zip-only",
        action="store_true",
        help="only create the ZIP from the existing mirror; do not download",
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
    parser.add_argument(
        "--ssh-timeout",
        type=int,
        default=SSH_TIMEOUT,
        help="seconds before the SSH guard is aborted (default: %(default)s)",
    )
    parser.add_argument(
        "--rsync-timeout",
        type=int,
        default=RSYNC_TIMEOUT,
        help="seconds without rsync I/O before it aborts (default: %(default)s)",
    )
    return parser.parse_args(argv)


def log(message: str) -> None:
    """Print a progress line when --verbose is set, flushed for log ordering."""
    if VERBOSE:
        print(message, flush=True)


def validate_value(kind: str, value: str, pattern) -> str:
    """Return value if it matches pattern, else raise.

    Database, build id and host end up in SSH/rsync command arguments, so
    restrict them to characters that cannot alter a remote shell command.
    """
    if not pattern.fullmatch(value):
        raise RuntimeError(f"invalid {kind}: {value!r}")
    return value


def prepare_target_dir(path: Path) -> Path:
    """Create the mirror directory and verify that it is usable.

    A marker file identifies directories owned by this tool. Refuse to use a
    non-empty directory without the marker, because --delete-excluded would
    delete its contents.
    """
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MIRROR_MARKER
    if not marker.exists():
        if any(path.iterdir()):
            raise RuntimeError(
                f"{path} is not empty and lacks {MIRROR_MARKER}; refusing to "
                "use it as a backup mirror (--delete-excluded would delete "
                "its contents)"
            )
        marker.touch()
    try:
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as e:
        raise RuntimeError(f"{path} is not writable: {e}") from e
    return marker


def lock_mirror(marker: Path):
    """Take an exclusive, non-blocking lock on the mirror for this process."""
    handle = marker.open("r")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        handle.close()
        raise RuntimeError(
            f"another odoo-sh-backup run is using {marker.parent}"
        ) from e
    return handle


def lock_existing_mirror(path: Path):
    """Lock a marked mirror for ZIP-only; never create the ownership marker.

    Marking an unowned directory here would let a later normal run treat it
    as a mirror and delete its contents with --delete-excluded.
    """
    if not path.is_dir():
        raise RuntimeError(f"{path} does not exist; nothing to zip")
    marker = path / MIRROR_MARKER
    if not marker.exists():
        return None
    return lock_mirror(marker)


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
        try:
            data = json.load(resp)
            value = data["result"][0]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"unexpected response from {url}") from e
    if not isinstance(value, str):
        # Same handled error path as for malformed JSON (see above).
        raise RuntimeError(f"unexpected response from {url}")  # noqa: TRY004
    return value


def resolve_db(host: str, db: str, build_id: str):
    """Return (database, build id).

    An explicit database is never looked up, and its build id is derived from
    its name, keeping both paired. Discovery only happens when no database
    was supplied.
    """
    if not db:
        log("discovering database/build id ...")
        db = discover_db(host)
    if not db:
        raise RuntimeError(f"cannot determine database/build id from {host}")
    derived_build_id = db.rsplit("-", 1)[-1]
    if build_id and build_id != derived_build_id:
        raise RuntimeError(f"build id {build_id!r} does not match database {db!r}")
    return db, derived_build_id


def detect_db(target_dir: Path) -> str:
    """Infer the database name from the mirror's *_daily.sql.gz file."""
    candidates = sorted(target_dir.glob("*_daily.sql.gz"))
    if len(candidates) != 1:
        raise RuntimeError(f"cannot determine the database in {target_dir}; pass --db")
    return candidates[0].name[: -len("_daily.sql.gz")]


def resolve_zip_file(target_dir: Path, zip_file):
    """Return the ZIP path, refusing locations inside the mirror directory.

    The mirror is cleaned with --delete-excluded on every sync, so a ZIP
    stored inside it would be deleted (potentially right before a failed
    sync) instead of being kept as the last restorable backup.
    """
    if zip_file is None:
        zip_file = target_dir.parent / f"{target_dir.name}.zip"
    # resolve() also expands symlinks (strict=False is the default on 3.6),
    # so a symlinked directory cannot smuggle the ZIP into the mirror.
    target_root = target_dir.resolve()
    zip_path = zip_file.resolve()
    if zip_path == target_root or target_root in zip_path.parents:
        raise RuntimeError("--zip-file must be outside --target-dir")
    return zip_file


def sync_backups(
    ssh_host: str,
    db: str,
    db_prefix: str,
    target_dir: Path,
    ssh_timeout: int,
    rsync_timeout: int,
) -> None:
    """Mirror the *_daily artifacts of the remote backup.daily directory.

    target_dir is dedicated to this mirror, so --delete-excluded also removes
    everything else in it (pre-update backups, files from previous build
    ids, ...), except for the mirror marker.
    """
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        raise RuntimeError("ssh not found in PATH")
    rsync_bin = shutil.which("rsync")
    if not rsync_bin:
        raise RuntimeError("rsync not found in PATH")

    # Refuse to mirror (and therefore delete) when the remote daily dump is
    # missing, e.g. during a botched deploy or with a stale build id.
    # ssh exits with 255 on its own errors (auth, connection), otherwise
    # with the remote command's exit status.
    remote_dump = shlex.quote(f"backup.daily/{db}_daily.sql.gz")
    log(f"checking {db}_daily.sql.gz on {ssh_host} ...")
    try:
        guard = subprocess.run(
            [ssh_bin, *SSH_OPTS, ssh_host, "test", "-f", remote_dump],
            check=False,
            stderr=subprocess.PIPE,
            timeout=ssh_timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ssh check on {ssh_host} timed out after {ssh_timeout}s"
        ) from e
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
            rsync_bin,
            "-avh",
            "--partial",
            "--progress",
            "--delete",
            "--delete-excluded",
            # Protect the marker before --exclude=* turns it into a deletion.
            f"--filter=P /{MIRROR_MARKER}",
            # Exact database first: a name without "-" is not matched by the
            # prefix pattern below. Then the prefix, so dailies of previous
            # build ids are still transferred and cleaned up.
            f"--include=/{db}_daily*",
            f"--include=/{db}_daily*/**",
            f"--include=/{db_prefix}-*_daily*",
            f"--include=/{db_prefix}-*_daily*/**",
            "--exclude=*",
            f"--timeout={rsync_timeout}",
            "-e",
            " ".join([ssh_bin, *SSH_OPTS]),
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
            else:
                print(
                    f"warning: {filestore_src} is missing; the ZIP will not "
                    "contain a filestore",
                    file=sys.stderr,
                    flush=True,
                )
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

    # Prepare and lock the mirror before touching anything, so concurrent runs
    # cannot sync and zip the same directory at the same time. ZIP-only must
    # not create the ownership marker in an unowned directory.
    if args.zip_only:
        lock = lock_existing_mirror(args.target_dir)
    else:
        lock = lock_mirror(prepare_target_dir(args.target_dir))
    try:
        zip_file = resolve_zip_file(args.target_dir, args.zip_file)

        if args.zip_only:
            db = validate_value(
                "database name", args.db or detect_db(args.target_dir), DB_RE
            )
            log(f"database: {db}")
            create_backup_zip(db, args.target_dir, zip_file)
            return

        validate_value("host", args.host, HOST_RE)
        db, build_id = resolve_db(args.host, args.db, args.build_id)
        validate_value("database name", db, DB_RE)
        validate_value("build id", build_id, BUILD_ID_RE)
        log(f"database: {db}")
        ssh_host = f"{build_id}@{args.host}"
        # Without the trailing build id, so dailies of previous builds still
        # match the filters and get deleted locally after a redeploy.
        db_prefix = db.rsplit("-", 1)[0]

        sync_backups(
            ssh_host,
            db,
            db_prefix,
            args.target_dir,
            args.ssh_timeout,
            args.rsync_timeout,
        )
        create_backup_zip(db, args.target_dir, zip_file)
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        ts = datetime.now().astimezone().isoformat()
        print(f"odoo-sh-backup failed at {ts}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
