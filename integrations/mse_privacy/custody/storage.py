"""Private local files for the synthetic custody prototype."""

from contextlib import closing, contextmanager
import os
from pathlib import Path
import sqlite3
import stat


class StoreUnavailable(RuntimeError):
    """A protected store cannot be safely opened."""


class PrivateDatabase:
    def __init__(self, root, application_id):
        self.root = Path(root).absolute()
        self.path = self.root / "store.sqlite3"
        self.uid = os.geteuid()
        self.application_id = application_id
        self.identity = self._directories()
        self.file_identity = None

    def _directories(self):
        try:
            if self.root.resolve(strict=True) != self.root:
                raise StoreUnavailable("Private root must be canonical")
            current, parent, *ancestors = (self.root, *self.root.parents)
            direct = current.lstat()
            owner = parent.lstat()
            if (
                not stat.S_ISDIR(direct.st_mode)
                or direct.st_uid != self.uid
                or stat.S_IMODE(direct.st_mode) != 0o700
                or not stat.S_ISDIR(owner.st_mode)
                or owner.st_uid != self.uid
                or owner.st_mode & 0o022
            ):
                raise StoreUnavailable("Private root or parent is unsafe")
            for path in ancestors:
                ancestor = path.lstat()
                if (
                    not stat.S_ISDIR(ancestor.st_mode)
                    or ancestor.st_uid not in (self.uid, 0)
                    or (
                        ancestor.st_mode & 0o022 and not ancestor.st_mode & stat.S_ISVTX
                    )
                ):
                    raise StoreUnavailable("Private root has an unsafe ancestor")
            return ((direct.st_dev, direct.st_ino), (owner.st_dev, owner.st_ino))
        except (OSError, RuntimeError):
            raise StoreUnavailable("Private root is unavailable") from None

    def _files(self):
        if self._directories() != self.identity:
            raise StoreUnavailable("Private root was replaced")
        identity = None
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                info = self.path.with_name(self.path.name + suffix).lstat()
            except FileNotFoundError:
                continue
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.uid
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
            ):
                raise StoreUnavailable("Private store file is unsafe")
            if not suffix:
                identity = (info.st_dev, info.st_ino)
        if self.file_identity is not None and identity != self.file_identity:
            raise StoreUnavailable("Private store was removed or replaced")
        return identity

    def create(self, schema):
        if self._files() is not None:
            raise StoreUnavailable("Private store already exists")
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
            )
            os.close(descriptor)
            self.file_identity = self._files()
            with closing(
                sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True)
            ) as db:
                db.executescript(
                    f"BEGIN IMMEDIATE; PRAGMA application_id={self.application_id};"
                    "PRAGMA user_version=1;" + schema + "COMMIT;"
                )
        except (OSError, sqlite3.Error):
            raise StoreUnavailable("Could not initialize private store") from None

    @contextmanager
    def open(self, *, write=False):
        try:
            identity = self._files()
        except OSError:
            raise StoreUnavailable("Private store is unavailable") from None
        try:
            if identity is None:
                raise StoreUnavailable("Private store is unavailable")
            self.file_identity = identity
            mode = "rw" if write else "ro"
            with closing(
                sqlite3.connect(
                    self.path.as_uri() + "?mode=" + mode,
                    uri=True,
                    timeout=2,
                )
            ) as db:
                if (
                    db.execute("PRAGMA application_id").fetchone()[0]
                    != self.application_id
                    or db.execute("PRAGMA user_version").fetchone()[0] != 1
                ):
                    raise StoreUnavailable(
                        "Private store has the wrong type or version"
                    )
                if write:
                    db.execute("PRAGMA synchronous=FULL")
                with db:
                    if write:
                        db.execute("BEGIN IMMEDIATE")
                    yield db
        except sqlite3.Error:
            raise StoreUnavailable("Private store is unavailable") from None
