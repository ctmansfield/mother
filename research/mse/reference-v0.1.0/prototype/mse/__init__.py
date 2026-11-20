"""Offline reference Metabolic State Engine; no treatment or network operations."""

__version__ = "0.1.0"
MODEL_VERSION = "mse-ou-reference/0.1.0"


def implementation_sha256():
    """Pin the exact executable Python source, independently of a release label."""
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parent
    evidence = b"".join(path.name.encode() + b"\0" + path.read_bytes() + b"\0"
                        for path in sorted(root.glob("*.py")))
    return hashlib.sha256(evidence).hexdigest()
