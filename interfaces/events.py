from typing import Dict, Any


class EventHandler:
    def on_event(self, ev: Dict[str, Any]) -> None:
        raise NotImplementedError
