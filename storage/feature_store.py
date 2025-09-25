import time


class FeatureStore:
    def materialize(self, context):
        # TODO: compute real rolling features; placeholder
        return {
            "hour": time.localtime().tm_hour,
            "streak_len": context.get("streak", 0),
        }
