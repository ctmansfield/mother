"""Shared bounded file and custody-path checks."""

from enum import Enum
from hashlib import sha256
import os
import stat

CHUNK = 64 * 1024


class InvalidHistory(ValueError):
    """Refuse an archive without exposing member or record values."""


class HistoryLimit(InvalidHistory):
    """A protected archive or catalog exceeded an approved resource bound."""


class LimitKind(Enum):
    ARCHIVE_BYTES = "ARCHIVE_BYTES_LIMIT"
    BINDING_BYTES = "BINDING_BYTES_LIMIT"
    CATALOG_BYTES = "CATALOG_BYTES_LIMIT"
    CATALOG_PAGES = "CATALOG_PAGE_LIMIT"
    FILE_SIZE = "FILE_SIZE_LIMIT"
    FILE_SIZE_CONFIGURATION = "FILE_SIZE_CONFIGURATION"
    FILESYSTEM_RESERVE = "FILESYSTEM_RESERVE_LIMIT"
    JOURNAL_BYTES = "JOURNAL_BYTES_LIMIT"
    SCRATCH_CAPACITY = "SCRATCH_CAPACITY_LIMIT"
    XML_CHILDREN = "XML_CHILD_LIMIT"
    XML_DEPTH = "XML_DEPTH_LIMIT"
    XML_DTD = "XML_DTD_LIMIT"
    XML_ELEMENTS = "XML_ELEMENT_LIMIT"
    XML_ROWS = "XML_ROW_LIMIT"
    XML_TOKEN = "XML_TOKEN_LIMIT"
    XML_TYPE_BUCKETS = "XML_TYPE_BUCKET_LIMIT"
    ZIP_DIRECTORY = "ZIP_DIRECTORY_LIMIT"
    ZIP_EXPANDED = "ZIP_EXPANDED_BYTES_LIMIT"
    ZIP_MEMBERS = "ZIP_MEMBER_COUNT_LIMIT"
    ZIP_MEMBER_BYTES = "ZIP_MEMBER_BYTES_LIMIT"
    ZIP_RATIO = "ZIP_RATIO_LIMIT"


class NamedHistoryLimit(HistoryLimit):
    """A named approved budget, with no input details in its public label."""

    def __init__(self, kind, message):
        if not isinstance(kind, LimitKind):
            raise TypeError("invalid resource limit category")
        super().__init__(message)
        self.kind = kind


def hash_stream(stream, limit, *, kind=None):
    digest = sha256()
    count = 0
    while chunk := stream.read(CHUNK):
        count += len(chunk)
        if count > limit:
            if kind is not None:
                raise NamedHistoryLimit(kind, "history byte limit exceeded")
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
