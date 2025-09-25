import json
import os


class PolicyState:
    def __init__(self, path="out/policy_state.json"):
        self.path = path
        self.state = {}
        if os.path.exists(path):
            try:
                self.state = json.load(open(path))
            except Exception:
                self.state = {}

    def get(self, k, default=None):
        return self.state.get(k, default)

    def set(self, k, v):
        self.state[k] = v
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump(self.state, open(self.path, "w"))
