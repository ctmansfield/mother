from __future__ import annotations

import argparse
import json
from mother.memory.adapter import MemoryAdapter


def cmd_upsert(args: argparse.Namespace) -> None:
    mem = MemoryAdapter()
    vid = mem.upsert(
        user_id=args.user,
        text=args.text,
        mtype=args.type,
        tags=args.tags,
        pin=args.pin,
        payload=json.loads(args.payload) if args.payload else None,
        confidence=float(args.confidence),
    )
    print(json.dumps({"id": vid, "ok": True}, ensure_ascii=False, default=str))


def cmd_search(args: argparse.Namespace) -> None:
    mem = MemoryAdapter()
    rows = mem.retrieve(
        user_id=args.user,
        query=args.query,
        limit=args.limit,
        types=args.types,
        tags=args.tags,
    )
    print(json.dumps({"results": rows}, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="mother memory CLI (pgvector)")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("upsert", help="upsert a memory item")
    u.add_argument("--user", required=True)
    u.add_argument("--text", required=True)
    u.add_argument(
        "--type",
        default="autobio",
        choices=["autobio", "episodic", "semantic", "procedural"],
    )
    u.add_argument("--tags", nargs="*", default=None)
    u.add_argument("--pin", action="store_true", default=False)
    u.add_argument("--payload", default=None, help="JSON string")
    u.add_argument("--confidence", default="0.9")
    u.set_defaults(func=cmd_upsert)

    s = sub.add_parser("search", help="search memory items")
    s.add_argument("--user", required=True)
    s.add_argument("--query", required=True)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--types", nargs="*", default=None)
    s.add_argument("--tags", nargs="*", default=None)
    s.set_defaults(func=cmd_search)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
