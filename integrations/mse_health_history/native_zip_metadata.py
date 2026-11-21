"""Read only central-directory totals from an already closed, private ZIP."""

import json
from pathlib import Path
import sys
from zipfile import BadZipFile, _EndRecData

from .files import InvalidHistory, NamedHistoryLimit, private_path
from .inventory import MAX_ZIP_MEMBERS, Limits, _check_zip_directory


def zip_metadata(path):
    path = Path(path).absolute()
    private_path(path, directory=False)
    with path.open("rb") as stream:
        directory = _EndRecData(stream)
        if directory is None:
            raise InvalidHistory("ZIP directory absent")
        return _check_zip_directory(stream, directory, Limits(members=MAX_ZIP_MEMBERS))


def main():
    if len(sys.argv) != 2:
        print("Use one approved private closed ZIP path", file=sys.stderr)
        return 2
    try:
        members, directory_bytes = zip_metadata(sys.argv[1])
    except NamedHistoryLimit as error:
        print(json.dumps({"status": "REFUSED", "category": error.kind.value}))
        return 1
    except (OSError, ValueError, BadZipFile):
        print(json.dumps({"status": "REFUSED", "category": "ARCHIVE_OR_XML"}))
        return 1
    print(
        json.dumps(
            {"member_count": members, "central_directory_bytes": directory_bytes}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
