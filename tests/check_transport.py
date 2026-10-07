"""Caller deadlines, overload, cleanup and signed-source fidelity."""
import json
import threading
import time
from haltseal_payments_sdk import Client, TransportError, UncertainDispatch, ValidationError
from haltseal_payments_sdk import _transport

class BlockingTransport:
    def __init__(self):
        self.release = threading.Event()
        self.calls = 0
        self.lock = threading.Lock()
    def open(self, request, *, timeout):
        with self.lock:
            self.calls += 1
        self.release.wait(5)
        raise OSError("synthetic blocked transport")
    def close(self):
        self.release.set()

# A custom adapter ignoring timeout must not hold up its caller or trigger a
# resend. A smaller injected budget exercises saturation without 64 threads.
old_slots = _transport._SLOTS
budget = threading.BoundedSemaphore(2)
_transport._SLOTS = budget
transport = BlockingTransport()
client = Client("http://127.0.0.1:1", "synthetic-key", timeout=.08, transport=transport)
try:
    for operation in ["blocked-1", "blocked-2"]:
        started = time.monotonic()
        try:
            client.create_attempt("test-obligation", operation_id=operation, route="A", approval_revision=1)
            raise AssertionError("Blocked transport returned")
        except UncertainDispatch as error:
            assert error.code == "DEADLINE_EXCEEDED"
            assert error.operation_id == operation and error.recovery.request_may_have_executed
            assert time.monotonic() - started < .8
    assert transport.calls == 2
    try:
        client.attempt("no-send-at-capacity")
        raise AssertionError("Transport overload was accepted")
    except ValidationError:
        pass
    assert transport.calls == 2
finally:
    client.close()
    assert budget.acquire(timeout=2) and budget.acquire(timeout=2), "Workers did not release their slots"
    budget.release(); budget.release()
    _transport._SLOTS = old_slots

class CapturedResponse:
    status = 200
    headers = {"Content-Type": "application/json"}
    def __init__(self, request): self.request = request
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def geturl(self): return self.request.full_url
    def read(self, size):
        return b'{"mode":"local-evaluation","production":"NO_GO","decision":"REGISTERED","reason":"SOURCE_IMPORTED","obligation_id":"test-obligation"}'
class CaptureTransport:
    def __init__(self): self.bodies = []
    def open(self, request, *, timeout):
        self.bodies.append(request.data)
        return CapturedResponse(request)
    def close(self): pass
capture = CaptureTransport()
raw = ' { "issued_at_ns": 1791376800000000000, "test_case": "raw-source" } \n'
with Client("http://127.0.0.1:1", "synthetic-key", transport=capture) as client:
    client.approve_source(raw)
    assert capture.bodies == [raw.encode()]
    try:
        client.approve_source(json.loads(raw))
        raise AssertionError("Signed source dict was rewritten")
    except ValidationError:
        pass
    assert len(capture.bodies) == 1

class BrokenCloseTransport:
    def open(self, request, *, timeout): raise OSError("synthetic unavailable")
    def close(self): raise OSError("synthetic cleanup failure")
try:
    with Client("http://127.0.0.1:1", "synthetic-key", transport=BrokenCloseTransport()) as client:
        client.create_attempt("test-obligation", operation_id="retain-on-close", route="A", approval_revision=1)
    raise AssertionError("Expected uncertainty")
except UncertainDispatch as error:
    assert error.operation_id == "retain-on-close"

print("PASS: Python total custom-transport deadlines, bounded overload, raw source fidelity, primary-error cleanup.")
