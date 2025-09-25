#!/usr/bin/env python3
import os
import json
import numpy as np
import scripts.weyland_hash as wh


def ensure_lambert_index():
    if not os.path.exists("out/lambert_index.json"):
        try:
            import scripts.lambert_index as L

            L.main()
        except Exception:
            json.dump({"index": []}, open("out/lambert_index.json", "w"))


def main(out_path="out/weyland_index.npz"):
    ensure_lambert_index()
    data = (
        json.load(open("out/lambert_index.json"))
        if os.path.exists("out/lambert_index.json")
        else {"index": []}
    )
    idx = data.get("index") or []
    ids = []
    vecs = []
    for r in idx:
        tid = r.get("id") or ""
        txt = r.get("text") or ""
        ids.append(tid)
        vecs.append(wh.embed(txt))
    if not ids:
        np.savez(
            out_path,
            ids=np.array([], dtype="U32"),
            vecs=np.zeros(
                (
                    0,
                    int(
                        (
                            __import__("yaml").safe_load(open("content/weyland.yaml"))
                            or {}
                        )
                        .get("weyland", {})
                        .get("dim", 512)
                    ),
                ),
                dtype=float,
            ),
        )
    else:
        np.savez(out_path, ids=np.array(ids, dtype="U32"), vecs=np.vstack(vecs))
    print({"built": len(ids), "out": out_path})


if __name__ == "__main__":
    main()
