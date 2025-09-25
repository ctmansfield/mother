from typing import Dict, Any, List


class Creative:
    def variants(
        self, context_card: Dict[str, Any], k: int = 3
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError
