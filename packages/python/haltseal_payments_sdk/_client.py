from __future__ import annotations
import hashlib
import ipaddress
import json
import math
import re
import threading
import time
from typing import Any, Callable, cast
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request
from ._types import PaymentResult, RecoveryContext, Transport
from ._transport import DeadlineExceeded, Exchange, TransportBusy

MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 16_384
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DECISIONS = {"ACCEPT", "HOLD", "REFUSE", "REGISTERED", "REVOKED", "OBSERVED"}
STATES = {"PREPARED", "EXPOSED", "PENDING", "IN_TRANSIT", "PAID", "CLOSED", "FAILED_REVIEW", "NEVER_DISPATCHED"}
MAX_SAFE_INTEGER = 9_007_199_254_740_991

class ValidationError(ValueError):
    """Invalid local input; this invocation was not sent."""

class APIError(Exception):
    def __init__(self, code: str, status: int, *, recovery: RecoveryContext | None = None,
                 request_id: str | None = None):
        self.code, self.status, self.recovery, self.request_id = code, status, recovery, request_id
        super().__init__(code)

class TransportError(Exception):
    def __init__(self, code: str, recovery: RecoveryContext, *, status: int | None = None,
                 request_id: str | None = None):
        self.code, self.recovery, self.status, self.request_id = code, recovery, status, request_id
        self.operation_id, self.attempt_id = recovery.operation_id, recovery.attempt_id
        self.obligation_id, self.recovery_action = recovery.obligation_id, recovery.action
        self.identity_kind, self.identity_value = recovery.identity_kind, recovery.identity_value
        self.request_fingerprint = recovery.request_fingerprint
        super().__init__("Response unavailable or invalid; follow the retained recovery context. No automatic retry.")

class UncertainDispatch(TransportError):
    """A modifying request may have committed. This grants no new send."""

def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValidationError("Identifier must contain 1-128 ASCII identifier characters")
    return value

def _revision(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= 9_007_199_254_740_991:
        raise ValidationError("approval_revision must be a positive safe integer")
    return value

def _strict_json(raw: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in items:
            if k in out:
                raise ValueError("Duplicate JSON key")
            out[k] = v
        return out
    def constant(value: str) -> None:
        raise ValueError("Nonfinite JSON value")
    def floating(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite JSON value")
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)

def _safe_integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= MAX_SAFE_INTEGER

def _enum(value: Any, allowed: set[str]) -> bool:
    return isinstance(value, str) and value in allowed

def _valid_attempt(data: Any, *, obligation_id: str | None = None) -> bool:
    if not isinstance(data, dict):
        return False
    for key in ["attempt_id", "obligation_id", "product_instance_id"]:
        if not isinstance(data.get(key), str) or not ID.fullmatch(data[key]):
            return False
    if obligation_id is not None and data["obligation_id"] != obligation_id:
        return False
    state = data.get("state")
    if not _enum(state, STATES) or not _enum(data.get("route"), {"A", "B", "C"}):
        return False
    if data.get("execution_outcome") != (state if state in {"PAID", "CLOSED"} else "UNKNOWN"):
        return False
    if not _safe_integer(data.get("amount_minor"), 1) or not _safe_integer(data.get("approval_revision"), 1):
        return False
    for key in ["ever_paid", "dispatch_intent_recorded"]:
        if type(data.get(key)) is not bool:
            return False
    if state == "PAID" and not data["ever_paid"] or state == "CLOSED" and data["ever_paid"]:
        return False
    if not {"original_payment_id", "source_evidence_digest", "source_status", "closure_profile"} <= data.keys():
        return False
    original = data["original_payment_id"]
    if original is not None and not (isinstance(original, str) and ID.fullmatch(original) or _safe_integer(original, 1)):
        return False
    evidence = data["source_evidence_digest"]
    if evidence is not None and (not isinstance(evidence, str) or not re.fullmatch(r"[a-f0-9]{64}", evidence)):
        return False
    for key in ["source_status", "closure_profile"]:
        if data[key] is not None and (not isinstance(data[key], str) or not data[key]):
            return False
    return True

def _valid_result(data: Any, context: RecoveryContext) -> bool:
    if not isinstance(data, dict) or data.get("mode") != "local-evaluation" or data.get("production") != "NO_GO":
        return False
    for key in ["attempt_id", "obligation_id", "operation_id"]:
        if key in data and (not isinstance(data[key], str) or not ID.fullmatch(data[key])):
            return False
    if "decision" in data and not _enum(data["decision"], DECISIONS):
        return False
    if "state" in data and not _enum(data["state"], STATES):
        return False
    if "execution_outcome" in data and not _enum(data["execution_outcome"], STATES | {"UNKNOWN", "PREPARED_BLOCKED"}):
        return False
    if ("decision" in data or "reason" in data) and not isinstance(data.get("reason"), str):
        return False
    for key in ["historical_decision", "redispatched", "ever_paid", "dispatch_intent_recorded"]:
        if key in data and type(data[key]) is not bool:
            return False
    for key, minimum in [("amount_minor", 1), ("approval_revision", 1), ("available_principal_minor", 0), ("maximum_source_debit_minor", 0)]:
        if key in data and not _safe_integer(data[key], minimum):
            return False
    kind = context.request_kind
    if kind == "approve_source":
        return _enum(data.get("decision"), {"REGISTERED", "REVOKED", "HOLD", "REFUSE"}) and (
            data["decision"] not in {"REGISTERED", "REVOKED"} or isinstance(data.get("obligation_id"), str))
    if kind == "obligation":
        if data.get("obligation_id") != context.obligation_id or not isinstance(data.get("attempts"), list):
            return False
        amount, available = data.get("amount_minor"), data.get("available_principal_minor")
        if not _safe_integer(amount, 1) or not _safe_integer(available) or available > amount:
            return False
        if not _safe_integer(data.get("approval_revision"), 1) or not _enum(data.get("approval_status"), {"APPROVED", "REVOKED"}):
            return False
        expiry = data.get("approval_expires_at_ns")
        if not isinstance(expiry, str) or not re.fullmatch(r"[0-9]+", expiry):
            return False
        seen: set[str] = set()
        for attempt in data["attempts"]:
            if not _valid_attempt(attempt, obligation_id=context.obligation_id):
                return False
            if attempt["attempt_id"] in seen or attempt["amount_minor"] != amount or attempt["approval_revision"] > data["approval_revision"]:
                return False
            seen.add(attempt["attempt_id"])
        return True
    if kind == "attempt":
        return data.get("attempt_id") == context.attempt_id and _valid_attempt(data)
    if kind == "lookup_operation":
        if context.obligation_id is not None and data.get("obligation_id") != context.obligation_id:
            return False
        # A blocked operation without an attempt can be a bare historical
        # decision. Financially accepted/record-bearing replies must bind an
        # obligation; an explicitly supplied binding is always required.
        if (data.get("decision") == "ACCEPT" or "attempt_id" in data or "attempt" in data) and not isinstance(data.get("obligation_id"), str):
            return False
        if data.get("operation_id") != context.operation_id or data.get("historical_decision") is not True or data.get("redispatched") is not False:
            return False
        nested = data.get("attempt")
        if data.get("attempt_id") is not None:
            if not _valid_attempt(nested) or nested["attempt_id"] != data["attempt_id"]:
                return False
            if "obligation_id" in data and nested["obligation_id"] != data["obligation_id"]:
                return False
        elif "attempt" in data:
            return False
        return _enum(data.get("decision"), {"ACCEPT", "HOLD", "REFUSE"}) and (
            data["decision"] != "ACCEPT" or "attempt_id" in data and "execution_outcome" in data)
    if kind == "create_attempt":
        if data.get("operation_id") != context.operation_id or data.get("obligation_id") != context.obligation_id:
            return False
        if data.get("historical_decision") is True and data.get("redispatched") is not False or data.get("redispatched") is True:
            return False
        if "attempt" in data and (not _valid_attempt(data["attempt"], obligation_id=context.obligation_id)
                                   or data["attempt"].get("attempt_id") != data.get("attempt_id")):
            return False
        return _enum(data.get("decision"), {"ACCEPT", "HOLD", "REFUSE"}) and (
            data["decision"] != "ACCEPT" or isinstance(data.get("attempt_id"), str) and "execution_outcome" in data)
    if kind in {"recover", "cancel", "resume"}:
        # The kernel's OBSERVED reply is an identity-bound status summary.
        # If an adapter expands it into a record, require the complete record.
        record_fields = {"obligation_id", "route", "product_instance_id", "execution_outcome",
                         "amount_minor", "approval_revision", "ever_paid", "dispatch_intent_recorded",
                         "original_payment_id", "source_evidence_digest", "source_status", "closure_profile"}
        observed = _enum(data.get("state"), STATES) and (
            not record_fields.intersection(data) or _valid_attempt(data))
        return _enum(data.get("decision"), {"HOLD", "REFUSE", "OBSERVED"}) and (
            data.get("attempt_id") == context.attempt_id) and (
            data["decision"] != "OBSERVED" or observed)
    return False

class Client:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30,
                 transport: Transport | None = None,
                 on_event: Callable[[dict[str, Any]], None] | None = None):
        if not isinstance(base_url, str) or not re.match(r"^https?://", base_url, re.I) or any(ord(c) <= 32 for c in base_url) or any(c in base_url for c in "\\?#"):
            raise ValidationError("A complete HTTPS origin or literal loopback HTTP origin is required")
        try:
            url = urlsplit(base_url)
            host, port = url.hostname, url.port
        except ValueError:
            raise ValidationError("Invalid origin") from None
        try:
            loopback = bool(host) and ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not host or url.scheme not in {"http", "https"} or (url.scheme == "http" and not loopback) or "@" in url.netloc or url.query or url.fragment or url.path not in {"", "/"} or (port is not None and port < 1):
            raise ValidationError("Use an HTTPS origin or literal loopback HTTP origin without credentials or a path")
        if not isinstance(api_key, str) or not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
            raise ValidationError("A nonempty ASCII API key without whitespace is required")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValidationError("timeout must be a finite positive number")
        if on_event is not None and not callable(on_event):
            raise ValidationError("on_event must be callable")
        if transport is not None and (not callable(getattr(transport, "open", None)) or not callable(getattr(transport, "close", None))):
            raise ValidationError("transport must implement one-send open and close")
        self.base_url, self.api_key, self.timeout = base_url.rstrip("/"), api_key, float(timeout)
        self.transport, self.on_event, self.closed = transport, on_event, False
        self._lock = threading.Lock()
        self._active: set[Exchange] = set()

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self.closed = True
            active = list(self._active)
        for exchange in active:
            exchange.cancel()
        if self.transport is not None:
            self.transport.close()

    def __enter__(self) -> Client:
        if self.closed:
            raise ValidationError("Client is closed")
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.close()
        else:
            # Cleanup must not replace the primary payment recovery exception.
            try:
                self.close()
            except Exception:
                pass

    def _request(self, method: str, path: str, body: Any = None, *, kind: str,
                 operation_id: str | None = None, obligation_id: str | None = None,
                 attempt_id: str | None = None, revision: int | None = None) -> PaymentResult:
        if self.closed:
            raise ValidationError("Client is closed")
        try:
            raw = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8") if body is not None else None
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ValidationError("JSON request required") from None
        if raw is not None and len(raw) > MAX_REQUEST_BYTES:
            raise ValidationError("Request exceeds the API's 16 KiB limit")
        action = "REPEAT_READ" if method == "GET" else "LOOKUP_OPERATION" if operation_id else "LOOKUP_ATTEMPT" if attempt_id else "REVIEW_SOURCE"
        identity_kind = "OPERATION_ID" if operation_id else "ATTEMPT_ID" if attempt_id else "OBLIGATION_ID" if obligation_id else "SOURCE_APPROVAL"
        fingerprint = hashlib.sha256(method.encode() + b"\n" + path.encode() + b"\n" + (raw or b"")).hexdigest()
        context = RecoveryContext(self.base_url, kind, action, identity_kind, operation_id or attempt_id or obligation_id,
                                  fingerprint, operation_id, obligation_id, attempt_id, revision, method == "POST")
        req = Request(self.base_url + path, data=raw, method=method,
                      headers={"Authorization": "Bearer " + self.api_key, "Accept": "application/json", "Content-Type": "application/json"})
        started, status, request_id, result_kind = time.monotonic(), None, None, "unknown"
        exchange = Exchange(started + self.timeout)
        with self._lock:
            if self.closed:
                raise ValidationError("Client is closed")
            self._active.add(exchange)
        def finished() -> None:
            with self._lock:
                self._active.discard(exchange)
        def failure(code: str) -> TransportError:
            cls = UncertainDispatch if method == "POST" else TransportError
            return cls(code, context, status=status, request_id=request_id)
        def consume(response: Any) -> PaymentResult:
            nonlocal status, request_id
            exchange.check()
            status = response.status if hasattr(response, "status") else response.code
            header_id = response.headers.get("X-Request-ID", "")
            request_id = header_id if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", header_id) else None
            if 300 <= status < 400:
                if method == "POST":
                    raise failure("REDIRECT_REFUSED")
                raise APIError("REDIRECT_REFUSED", status, recovery=context, request_id=request_id)
            if status >= 500 or status in {408, 429}:
                raise failure("HTTP_" + str(status))
            if response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise failure("INVALID_CONTENT_TYPE")
            length = response.headers.get("Content-Length")
            if hasattr(response.headers, "get_all") and len(response.headers.get_all("Content-Length", [])) > 1:
                raise failure("AMBIGUOUS_RESPONSE_LENGTH")
            if length is not None and (not re.fullmatch(r"[0-9]+", length) or int(length) > MAX_RESPONSE_BYTES):
                raise failure("RESPONSE_TOO_LARGE_OR_INVALID_LENGTH")
            if response.geturl() != req.full_url:
                raise failure("REDIRECT_REFUSED")
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise failure("RESPONSE_TOO_LARGE")
            if length is not None and len(data) != int(length):
                raise failure("INCOMPLETE_RESPONSE")
            parsed = _strict_json(data.decode("utf-8"))
            exchange.check()
            if status >= 400:
                code = parsed.get("error") if isinstance(parsed, dict) else None
                if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,128}", code):
                    raise failure("INVALID_ERROR_RESPONSE")
                raise APIError(code, status, recovery=context, request_id=request_id)
            if status != 200 or not _valid_result(parsed, context):
                raise failure("INVALID_RESPONSE_CONTRACT")
            return cast(PaymentResult, parsed)
        def send_once() -> PaymentResult:
            try:
                with exchange.open(req, self.transport) as response:
                    return consume(response)
            except HTTPError as exc:
                with exc:
                    return consume(exc)
        try:
            result = exchange.call(send_once, finished)
            result_kind = "response"
            return result
        except TransportBusy:
            finished()
            raise ValidationError("SDK transport capacity exhausted; this invocation was not sent") from None
        except DeadlineExceeded:
            raise failure("DEADLINE_EXCEEDED") from None
        except APIError as exc:
            if exc.recovery is not context:
                raise failure("TRANSPORT_OR_RESPONSE_UNCERTAIN") from None
            result_kind = "api_error"
            raise
        except TransportError as exc:
            if exc.recovery is not context:
                raise failure("TRANSPORT_OR_RESPONSE_UNCERTAIN") from None
            raise
        except Exception:
            raise failure("TRANSPORT_OR_RESPONSE_UNCERTAIN") from None
        finally:
            if self.on_event is not None:
                event = {"request_kind": kind, "request_fingerprint": fingerprint, "request_id": request_id,
                         "status": status, "result": result_kind, "duration_ms": round((time.monotonic() - started) * 1000, 3)}
                try:
                    self.on_event(event)
                except Exception:
                    pass

    def approve_source(self, envelope: str) -> PaymentResult:
        if not isinstance(envelope, str):
            raise ValidationError("Original signed source JSON string required")
        try:
            parsed = _strict_json(envelope)
        except (ValueError, RecursionError):
            raise ValidationError("Original signed source JSON required") from None
        if not isinstance(parsed, dict):
            raise ValidationError("Signed source envelope object required")
        return self._request("POST", "/v1/payment-obligations", envelope, kind="approve_source")

    def obligation(self, obligation_id: str) -> PaymentResult:
        value = _identifier(obligation_id)
        return self._request("GET", "/v1/payment-obligations/" + quote(value, safe=""), kind="obligation", obligation_id=value)

    def create_attempt(self, obligation_id: str, *, operation_id: str, route: str, approval_revision: int) -> PaymentResult:
        oid, op, selected, rev = _identifier(obligation_id), _identifier(operation_id), _identifier(route), _revision(approval_revision)
        if selected not in {"A", "B", "C"}:
            raise ValidationError("route must be A, B or C in this evaluation profile")
        return self._request("POST", "/v1/payment-obligations/" + quote(oid, safe="") + "/attempts",
                             {"operation_id": op, "route": selected, "approval_revision": rev}, kind="create_attempt",
                             operation_id=op, obligation_id=oid, revision=rev)

    def lookup_operation(self, operation_id: str, *, obligation_id: str | None = None) -> PaymentResult:
        op = _identifier(operation_id)
        oid = _identifier(obligation_id) if obligation_id is not None else None
        return self._request("GET", "/v1/payment-attempts/lookup?" + urlencode({"operation_id": op}), kind="lookup_operation", operation_id=op, obligation_id=oid)

    def attempt(self, attempt_id: str) -> PaymentResult:
        aid = _identifier(attempt_id)
        return self._request("GET", "/v1/payment-attempts/" + quote(aid, safe=""), kind="attempt", attempt_id=aid)

    def recover(self, attempt_id: str) -> PaymentResult:
        return self._action("recover", attempt_id)

    def cancel(self, attempt_id: str) -> PaymentResult:
        return self._action("cancel", attempt_id)

    def resume(self, attempt_id: str, *, approval_revision: int) -> PaymentResult:
        return self._action("resume", attempt_id, _revision(approval_revision))

    def _action(self, kind: str, attempt_id: str, revision: int | None = None) -> PaymentResult:
        aid = _identifier(attempt_id)
        body = {"approval_revision": revision} if kind == "resume" else {}
        return self._request("POST", "/v1/payment-attempts/" + quote(aid, safe="") + "/" + kind, body,
                             kind=kind, attempt_id=aid, revision=revision)
