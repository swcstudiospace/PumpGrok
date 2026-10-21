"""Persisted HMAC key for doctor agent bindings (WR-06).

Bindings are written under ``<data_dir>/bindings`` and must still verify after
a restart, so the key that minted them has to outlive the process. The key is
32 random bytes, hex encoded, stored at ``<data_dir>/binding.key``:

* created once, with mode 0600, via a fully written temp file hard-linked into
  place (so concurrent first boots agree on one key and never see a partial);
* reused on every later start;
* refused (fail closed) when the file is not a regular file, is a symlink, has
  any group or other permission bit set, or does not decode to 32 bytes.

The key is never written into the repository; the data dir is runtime state.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from pathlib import Path

__all__ = ["BINDING_KEY_FILENAME", "BindingKeyError", "load_or_create_binding_key"]

BINDING_KEY_FILENAME = "binding.key"
_KEY_BYTES = 32
_LOOSE_MODE_BITS = 0o077


class BindingKeyError(RuntimeError):
    """The persisted binding key is unusable; the process must not start."""


def load_or_create_binding_key(data_dir: Path) -> bytes:
    """Return the persisted binding key under ``data_dir``, creating it once."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / BINDING_KEY_FILENAME
    if not path.exists():
        _create_key(path)
    return _read_key(path)


def _create_key(path: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(os.urandom(_KEY_BYTES).hex() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        with contextlib.suppress(FileExistsError):
            # A concurrent first boot may have won the race; its key is the one to read.
            os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_key(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:  # includes ELOOP for a symlinked key file
        raise BindingKeyError(f"cannot open binding key {path}: {exc.strerror}") from exc
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise BindingKeyError(f"binding key {path} is not a regular file")
        if st.st_mode & _LOOSE_MODE_BITS:
            raise BindingKeyError(
                f"binding key {path} is group/other accessible "
                f"(mode {stat.S_IMODE(st.st_mode):04o}); expected 0600, refusing to start"
            )
        raw = fh.read()
    try:
        key = bytes.fromhex(raw.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise BindingKeyError(f"binding key {path} is not hex encoded") from exc
    if len(key) != _KEY_BYTES:
        raise BindingKeyError(f"binding key {path} must decode to {_KEY_BYTES} bytes")
    return key
