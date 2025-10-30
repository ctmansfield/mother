#!/usr/bin/env python3
import os
from analytics.preprocess.sources.nightscout_adapter import incremental_sync

if __name__ == "__main__":
    days = int(os.getenv("NS_SYNC_DAYS", "14"))
    out = incremental_sync(days=days)
    print(out)
