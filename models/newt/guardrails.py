from datetime import datetime, time


def _parse_secs(s: str) -> int:
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    return int(s)


class NewtGuard:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.last = {}
        self.sent_today = 0

    def in_quiet(self, now=None):
        now = now or datetime.now()
        for span in self.cfg.get("quiet_hours", []):
            start, end = span.split("-")
            s = time.fromisoformat(start)
            e = time.fromisoformat(end)
            if s <= now.time() or now.time() <= e:
                return True
        return False

    def allow(self, category: str, now=None):
        now = now or datetime.now()
        if self.sent_today >= self.cfg.get("budget_per_day", 6):
            return False, "budget"
        cd = (self.cfg.get("cooldowns") or {}).get(category)
        if cd:
            last = self.last.get(category)
            if last and (now - last).total_seconds() < _parse_secs(cd):
                return False, "cooldown"
        if self.in_quiet(now):
            return False, "quiet"
        return True, "ok"

    def record(self, category: str, now=None):
        now = now or datetime.now()
        self.last[category] = now
        self.sent_today += 1
