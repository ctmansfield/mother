"""Scoped byte relay. TLS stays end to end and terminates in the archive guest."""

from datetime import datetime, timezone
import ipaddress
import json
import selectors
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

CAP = 8
MAX_BYTES = 16 * 1024 * 1024
MAX_SECONDS = 45


class Relay(socketserver.ThreadingTCPServer):
    daemon_threads = True
    request_queue_size = CAP
    allow_reuse_address = False

    def process_request(self, request, client_address):
        if client_address[0] not in self.sources or not self.slots.acquire(
            blocking=False
        ):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # No addresses, payloads, tokens or request errors in routine logs.
        pass


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        remaining = self.server.remaining
        allowed = remaining()
        if allowed <= 0:
            return
        client = self.request
        with (
            socket.create_connection(
                (self.server.guest_ip, 8446),
                timeout=min(3, allowed),
                source_address=(self.server.bridge_ip, 0),
            ) as upstream,
            selectors.DefaultSelector() as sel,
        ):
            sel.register(client, selectors.EVENT_READ, upstream)
            sel.register(upstream, selectors.EVENT_READ, client)
            limit = time.monotonic() + MAX_SECONDS
            total = 0
            while sel.get_map():
                allowed = min(remaining(), limit - time.monotonic())
                if allowed <= 0:
                    return
                for key, _ in sel.select(timeout=min(1, allowed)):
                    allowed = min(remaining(), limit - time.monotonic())
                    if allowed <= 0:
                        return
                    key.fileobj.settimeout(min(3, allowed))
                    data = key.fileobj.recv(32768)
                    allowed = min(remaining(), limit - time.monotonic())
                    if allowed <= 0:
                        return
                    if not data:
                        sel.unregister(key.fileobj)
                        key.data.shutdown(socket.SHUT_WR)
                        continue
                    total += len(data)
                    if total > MAX_BYTES:
                        return
                    key.data.settimeout(min(3, allowed))
                    key.data.sendall(data)


def main(path):
    config = json.loads(Path(path).read_text())
    bind = config["host"]
    phone = config["phone"]
    subnet = ipaddress.ip_network("100.64.0.0/10")
    if bind == phone or any(
        ipaddress.ip_address(x) not in subnet for x in (bind, phone)
    ):
        raise ValueError("Expected distinct pinned tailnet addresses")
    expiry = datetime.fromisoformat(config["expiry"].replace("Z", "+00:00"))
    remaining_utc = (expiry - datetime.now(timezone.utc)).total_seconds()
    if remaining_utc <= 0:
        raise ValueError("Pilot relay deadline has passed")
    monotonic_limit = time.monotonic() + remaining_utc

    def remaining():
        return min(
            (expiry - datetime.now(timezone.utc)).total_seconds(),
            monotonic_limit - time.monotonic(),
        )

    with Relay((bind, 8446), Forward) as relay:
        relay.guest_ip = str(ipaddress.IPv4Address(config["guest_ip"]))
        relay.bridge_ip = str(ipaddress.IPv4Address(config["bridge_ip"]))
        relay.remaining = remaining
        relay.sources = {bind, phone} if config["phone_enabled"] else {bind}
        relay.slots = threading.BoundedSemaphore(CAP)
        while (available := remaining()) > 0:
            relay.timeout = min(1, available)
            relay.handle_request()


if __name__ == "__main__":
    main(sys.argv[1])
