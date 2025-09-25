from mother_core import event_bus


def start():
    print("Mother Core online.")
    event_bus.publish({"kind": "startup", "ts": 0})


if __name__ == "__main__":
    start()
