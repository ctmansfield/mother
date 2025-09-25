import yaml
import os


def load(path="content/policy.yaml"):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f)
