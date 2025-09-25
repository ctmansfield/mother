from typing import Dict, Any, List


class Policy:
    def choose(
        self, context: Dict[str, Any], candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        raise NotImplementedError
