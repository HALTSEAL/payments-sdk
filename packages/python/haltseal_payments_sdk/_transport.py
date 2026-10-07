"""One-send transport with a caller deadline and bounded background work.

The deadline includes DNS, connection/TLS, headers, body and validation. A
timed-out modifying call stays uncertain, including when a custom transport
cannot be interrupted. No background work is allowed to initiate a retry.
"""
from __future__ import annotations
from contextlib import contextmanager
import http.client
import queue
import socket
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import Request

# A stalled resolver or caller-supplied transport cannot create unlimited
# abandoned threads. The slot remains held until its original worker exits.
_SLOTS = threading.BoundedSemaphore(64)


class DeadlineExceeded(TimeoutError):
    pass


class TransportBusy(RuntimeError):
    pass


class _ConnectionGuard:
    exchange: Exchange

    def connect(self) -> None:
        self.exchange.check()
        super().connect()
        self.exchange.track(self.sock)
        self.exchange.check()

    def send(self, data: Any) -> None:
        self.exchange.check()
        super().send(data)


class _HTTPConnection(_ConnectionGuard, http.client.HTTPConnection):
    pass


class _HTTPSConnection(_ConnectionGuard, http.client.HTTPSConnection):
    pass


class _Response:
    def __init__(self, response: http.client.HTTPResponse, url: str):
        self.response, self.url = response, url
        self.status, self.headers = response.status, response.headers

    def geturl(self) -> str:
        return self.url

    def read(self, size: int) -> bytes:
        return self.response.read(size)


class Exchange:
    def __init__(self, deadline: float):
        self.deadline = deadline
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.sock: socket.socket | None = None

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise DeadlineExceeded()
        return remaining

    def check(self) -> None:
        if self.cancelled.is_set() or time.monotonic() >= self.deadline:
            raise DeadlineExceeded()

    def track(self, sock: socket.socket | None) -> None:
        with self.lock:
            self.sock = sock
            cancelled = self.cancelled.is_set()
        if cancelled:
            self.cancel()

    def cancel(self) -> None:
        self.cancelled.set()
        with self.lock:
            sock = self.sock
            self.sock = None
        if sock is not None:
            # shutdown interrupts a blocked header/body read; close alone may
            # leave the HTTPResponse's file descriptor alive on another thread.
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    @contextmanager
    def open(self, request: Request, transport: Any):
        self.check()
        if transport is not None:
            with transport.open(request, timeout=self.remaining()) as response:
                self.check()
                yield response
            return
        url = urlsplit(request.full_url)
        cls = _HTTPSConnection if url.scheme == "https" else _HTTPConnection
        connection = cls(url.hostname, url.port, timeout=self.remaining())
        connection.exchange = self
        try:
            path = url.path or "/"
            if url.query:
                path += "?" + url.query
            connection.request(request.get_method(), path, body=request.data,
                               headers=dict(request.header_items()))
            self.check()
            with connection.getresponse() as response:
                self.check()
                yield _Response(response, request.full_url)
        finally:
            connection.close()
            with self.lock:
                self.sock = None

    def call(self, work: Callable[[], Any], finished: Callable[[], None]) -> Any:
        slots = _SLOTS
        if not slots.acquire(blocking=False):
            raise TransportBusy()
        result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                value = work()
                self.check()
                result.put((True, value))
            except Exception as error:
                result.put((False, error))
            finally:
                try:
                    finished()
                finally:
                    slots.release()

        worker = threading.Thread(target=run, name="haltseal-sdk-send", daemon=True)
        try:
            worker.start()
        except Exception:
            slots.release()
            finished()
            raise TransportBusy() from None
        try:
            ok, value = result.get(timeout=self.remaining())
            self.check()
        except (queue.Empty, DeadlineExceeded):
            self.cancel()
            raise DeadlineExceeded() from None
        if ok:
            return value
        raise value
