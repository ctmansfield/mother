"""Publish exact native BP batches and private accounting on the custodian volume."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .files import private_path
from .native_runner import private_bytes
from .typed_vm import (
    MAX_BYTES,
    SCOPE,
    digest,
    encoded,
    is_ref,
    project,
    require,
    valid_clock,
)

FIELDS = {"scope", "bounds", "mapping_key_file", "output", "max_batches", "max_bytes"}


def validate_projection(projection, enrollment):
    require(
        isinstance(projection, dict)
        and set(projection) == FIELDS
        and set(projection["scope"]) == set(SCOPE)
        and all(is_ref(value) for value in projection["scope"].values())
        and projection["scope"]["enrollment_id"] == enrollment
        and isinstance(projection["bounds"], list)
        and len(projection["bounds"]) == 2
        and all(map(valid_clock, projection["bounds"]))
        and projection["bounds"][0] < projection["bounds"][1]
        and type(projection["max_batches"]) is int
        and 1 <= projection["max_batches"] <= 1024
        and type(projection["max_bytes"]) is int
        and 1 <= projection["max_bytes"] <= 512 * MAX_BYTES,
        "invalid native Mac projection request",
    )


def protected_destination(projection, mount, catalog, scratch):
    output = Path(projection["output"])
    require(output.is_absolute(), "exact native projection path required")
    private_path(output.parent, directory=True)
    require(
        mount in output.parents
        and output.parent.stat().st_dev == mount.stat().st_dev
        and catalog not in output.parents
        and scratch not in output.parents
        and output not in catalog.parents
        and output not in scratch.parents
        and not os.path.lexists(output),
        "fresh native projection destination on the pinned volume required",
    )
    return output


def _durable_file(path, raw):
    with os.fdopen(
        os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
    ) as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_projection(
    catalog, original_sha256, plan, output, *, mapping_key, prepublish
):
    """Make an entire immutable batch set visible in one protected rename."""
    ledger = []
    size = 0
    entries = []
    with TemporaryDirectory(prefix=".native-projection-", dir=output.parent) as scratch:
        stage = Path(scratch) / "ready"
        stage.mkdir(mode=0o700)
        batches = stage / "batches"
        batches.mkdir(mode=0o700)
        for seq, body in enumerate(
            project(
                catalog,
                original_sha256,
                plan["scope"],
                tuple(plan["bounds"]),
                mapping_key=mapping_key,
                record_accounting=ledger.append,
            ),
            1,
        ):
            size += len(body)
            require(
                seq <= plan["max_batches"] and size <= plan["max_bytes"],
                "native Mac projection quota",
            )
            name = f"{seq:04d}.json"
            _durable_file(batches / name, body)
            entries.append(
                {
                    "sequence": seq,
                    "file": name,
                    "bytes": len(body),
                    "sha256": digest(body),
                }
            )
        require(len(ledger) == 1, "native Mac projection reconciliation absent")
        _durable_file(
            stage / "private-accounting.json",
            encoded({"accounting": ledger[0], "batches": entries}),
        )
        _fsync_dir(batches)
        _fsync_dir(stage)
        prepublish()
        require(
            not os.path.lexists(output), "native Mac projection destination occupied"
        )
        os.rename(stage, output)
        _fsync_dir(output.parent)


def mapping_key(plan, approval, provenance):
    key = private_bytes(plan["mapping_key_file"], 32)
    require(
        len(key) == 32 and key != approval and key != provenance,
        "independent native mapping key required",
    )
    return key


def publish_universal(catalog, original_sha256, plan, output, *, prepublish):
    """Stage the authenticated universal catalog as complete canonical frames."""
    from .native_universal_transfer import export_catalog

    with TemporaryDirectory(prefix=".native-universal-", dir=output.parent) as scratch:
        stage = Path(scratch) / "ready"
        stage.mkdir(mode=0o700)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        with os.fdopen(
            os.open(stage / "exact-source.frames", flags, 0o600), "wb"
        ) as file:
            manifest = export_catalog(
                catalog,
                original_sha256,
                file,
                import_ref=plan["import_ref"],
                max_bytes=plan["max_bytes"],
            )
            file.flush()
            os.fsync(file.fileno())
        _durable_file(stage / "private-manifest.json", encoded(manifest))
        _fsync_dir(stage)
        prepublish()
        require(not os.path.lexists(output), "native universal destination occupied")
        os.rename(stage, output)
        _fsync_dir(output.parent)
