"""Admit mutable worker state only on identified local filesystem types."""

from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys

LOCAL_TYPES = frozenset(
    {"ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs", "zfs", "tmpfs", "apfs", "hfs"}
)
STATE_FILES = (
    "worker.lock",
    "manifest.json",
    "status.json",
    "result.json",
    "verification.json",
    "checkpoints.sqlite",
    "checkpoints.sqlite-wal",
    "checkpoints.sqlite-shm",
    "model-requests.json",
    "model-requests.lock",
)


class StorageError(ValueError):
    """The worker cannot establish an admitted location for mutable state."""


def _command(argv, *, binary=False):
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            timeout=10,
            check=True,
            **({} if binary else {"encoding": "utf-8"}),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise StorageError(
            "Cannot identify state filesystem using native metadata tools."
        ) from error
    return result.stdout


def filesystem_type(path: Path) -> str:
    """Read native mount metadata for an existing path, without shell evaluation."""
    if sys.platform.startswith("linux"):
        kind = _command(
            [
                "findmnt",
                "--first-only",
                "--noheadings",
                "--output",
                "FSTYPE",
                "--target",
                str(path),
            ]
        ).strip()
    elif sys.platform == "darwin":
        lines = _command(["/bin/df", "-P", str(path)]).splitlines()
        fields = lines[-1].split() if len(lines) >= 2 else []
        device = fields[0] if fields else ""
        if not re.fullmatch(r"/dev/disk[0-9]+(?:s[0-9]+)*", device):
            raise StorageError("State is not on an identifiable local macOS disk.")
        try:
            metadata = plistlib.loads(
                _command(
                    [
                        "/usr/sbin/diskutil",
                        "info",
                        "-plist",
                        device,
                    ],
                    binary=True,
                )
            )
            kind = metadata.get("FilesystemType")
        except (ValueError, TypeError, AttributeError) as error:
            raise StorageError("Invalid native filesystem metadata.") from error
    else:
        raise StorageError(
            "Filesystem admission is implemented for Linux and macOS only."
        )
    if not isinstance(kind, str) or not re.fullmatch(r"[a-zA-Z0-9_+.-]{1,32}", kind):
        raise StorageError("Native metadata did not identify one filesystem type.")
    return kind.lower()


def _require_local(path):
    kind = filesystem_type(path)
    if kind not in LOCAL_TYPES:
        raise StorageError(
            f"Run state filesystem {kind!r} is not admitted; use a supported local "
            "--run-dir. SQLite WAL must not use network storage."
        )
    return kind


def admit_state_directory(directory: Path) -> str:
    """Check the nearest existing directory and existing control files, without writes.

    This is a filesystem-type admission check, not a defense against privileged
    remounts/path replacement or a proof of hardware durability. tmpfs is volatile.
    """
    directory = Path(directory)
    if directory.is_symlink() and not directory.exists():
        raise StorageError("Run directory is a dangling symbolic link.")
    try:
        resolved = directory.resolve()
    except (OSError, RuntimeError) as error:
        raise StorageError("Cannot resolve run directory.") from error
    ancestor = resolved
    while not ancestor.exists():
        if ancestor == ancestor.parent:
            raise StorageError("Cannot find an existing state-directory ancestor.")
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise StorageError("Run state must be a directory.")
    kind = _require_local(ancestor)
    if resolved.exists():
        for name in STATE_FILES:
            path = resolved / name
            if path.is_symlink():
                raise StorageError(
                    f"Run control file {name!r} must not be a symbolic link."
                )
            if path.exists():
                if not stat.S_ISREG(path.stat().st_mode):
                    raise StorageError(
                        f"Run control file {name!r} must be an ordinary file."
                    )
                _require_local(path)
    return kind
