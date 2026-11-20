"""Reproduce public synthetic HealthKit-shaped fixture. Contains no personal data."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import UUID

root = Path(__file__).resolve().parent.parent
epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
start = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
heart_rate = [60, 61, 59, 60, 60, 61, 59, 60, 90, 80, 72, 64, 61]
sdnn = [50, 51, 49, 50, 50, 51, 49, 50, 25, 30, 35, 43, 48]
readings = []
for i, (hr, hrv) in enumerate(zip(heart_rate, sdnn)):
    seconds = (start + timedelta(minutes=15 * i) - epoch).total_seconds()
    for channel, value, unit, offset in (("Heart rate", hr, "bpm", 1), ("HRV (SDNN)", hrv, "ms", 101)):
        readings.append({"id": str(UUID(int=offset + i)), "kind": channel, "value": value,
                         "unit": unit, "start": seconds, "end": seconds + 60,
                         "source": "SYNTHETIC WATCH — NO HUMAN DATA", "bundleID": "example.synthetic.watch",
                         "receivedAt": seconds + 90})
fixture = {"readings": readings, "anchors": {"heartRate": "AQID", "hrvSDNN": "BAUG"},
           "tombstones": {}, "backfillStart": (start - epoch).total_seconds()}
destination = root / "examples" / "synthetic_healthkit_v03.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(fixture, sort_keys=True, indent=2) + "\n")
print("Reproduced 26 synthetic observations")
