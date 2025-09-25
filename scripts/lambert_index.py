#!/usr/bin/env python3
import os
import json
import re
import hashlib


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


WORD = re.compile(r"[A-Za-z][A-Za-z0-9']+")


def tokenize(s, stop):
    toks = [t.lower() for t in WORD.findall(s or "")]
    return [t for t in toks if t not in stop]


def main():
    cfg = (load_yaml("content/lambert.yaml") or {}).get("lambert", {})
    sources = cfg.get("sources", [])
    stop = set((cfg.get("stopwords") or []))
    index = []
    for src in sources:
        data = load_yaml(src) or {}
        # expect top-level categories mapping to list[str|dict]
        for cat, items in (data.items() if isinstance(data, dict) else []):
            if not isinstance(items, list):
                continue
            for i, it in enumerate(items):
                if isinstance(it, str):
                    text = it
                    tone = None
                    segs = []
                elif isinstance(it, dict):
                    text = it.get("text", "").strip()
                    tone = (it.get("tags") or {}).get("tone")
                    segs = (it.get("tags") or {}).get("segments") or []
                else:
                    continue
                if not text:
                    continue
                toks = tokenize(text, stop)
                hid = hashlib.sha1((cat + "|" + text).encode("utf-8")).hexdigest()[:12]
                rec = {
                    "id": f"{cat}#" + hid,
                    "category": cat,
                    "text": text,
                    "tokens": toks,
                    "tone": tone,
                    "segments": segs,
                }
                index.append(rec)
    os.makedirs("out", exist_ok=True)
    json.dump({"index": index}, open("out/lambert_index.json", "w"))
    print({"built": len(index), "out": "out/lambert_index.json"})


if __name__ == "__main__":
    main()
