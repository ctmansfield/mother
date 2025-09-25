handlers = {}


def subscribe(event_kind, fn):
    handlers.setdefault(event_kind, []).append(fn)


def publish(ev):
    for fn in handlers.get(ev.get("kind"), []):
        try:
            fn(ev)
        except Exception as e:
            print("handler error:", e)
