"""Strict capture validation for a separately reviewed manual wrapper."""

from .files import LimitKind

SUCCESS = b"Protected native catalog receipt verified\n"
DIAGNOSTIC_PREFIX = b"Protected native import category "
CATEGORIES = frozenset(
    {
        "ADMISSION",
        "ENVIRONMENT",
        "BINDING",
        "AUTHENTICATION",
        "ARCHIVE_OR_XML",
        "CATALOG",
        "PRECOMMIT_WINDOW",
        "PROJECTION",
        "COMMIT",
        "READBACK",
        "INVENTORY_LIMIT",
        "RESOURCE_LIMIT",
        "RUNTIME_LIMIT",
        "FILESYSTEM_FULL",
        "FILESYSTEM_QUOTA",
        "SQLITE_FULL",
        *(kind.value for kind in LimitKind),
    }
)


def capture_status(exit_code, stdout, stderr):
    """Accept one complete allowlisted line and withhold all mixed output."""
    if exit_code == 0 and stdout == SUCCESS and stderr == b"":
        return "RUNNER_REPORTED_SUCCESS", None
    if exit_code == 1 and stdout == b"":
        for label in CATEGORIES:
            if stderr == DIAGNOSTIC_PREFIX + label.encode("ascii") + b"\n":
                return "REFUSED", label
    return "UNCLASSIFIED", None
