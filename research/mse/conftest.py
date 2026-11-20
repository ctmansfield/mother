"""Keep the immutable offline MSE reference outside MOTHER pytest discovery.

Run its standalone verification explicitly from reference-v0.1.0/prototype:
    python3 -B -m unittest discover -s tests -v

This archive is not installed into the MOTHER runtime or its test environment.
"""

collect_ignore = ["reference-v0.1.0"]
