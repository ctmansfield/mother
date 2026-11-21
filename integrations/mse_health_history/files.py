"""Shared bounded file and custody-path checks."""

from hashlib import sha256
import os
import stat

CHUNK = 64 * 1024


class InvalidHistory(ValueError):
    """Refuse an archive without exposing member or record values."""


class HistoryLimit(InvalidHistory):
    """A protected archive or catalog exceeded an approved resource bound."""


def hash_stream(stream, limit):
    digest = sha256()
    count = 0
    while chunk := stream.read(CHUNK):
        count += len(chunk)
        if count > limit:
            raise HistoryLimit("history byte limit exceeded")
        digest.update(chunk)
    return digest.hexdigest(), count


def private_path(path, *, directory):
    info = path.lstat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        path.resolve(strict=True) != path
        or not expected_type(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
        or (not directory and info.st_nlink != 1)
    ):
        raise InvalidHistory("history custody path must be private")
