from __future__ import annotations
import hashlib
import ipaddress
import json
import math
import re
import time
from typing import Any, Callable, cast
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from ._types import PaymentResult, RecoveryContext, Transport

MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 16_384
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DECISIONS = {"ACCEPT", "HOLD", "REFUSE", "REGISTERED", "REVOKED", "OBSERVED"}
STATES = {"PREPARED", "EXPOSED", "PENDING", "IN_TRANSIT", "PAID", "CLOSED", "FAILED_REVIEW", "NEVER_DISPATCHED"}

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

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None

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

def _valid_result(data: Any, context: RecoveryContext) -> bool:
    if not isinstance(data, dict) or data.get("mode") != "local-evaluation" or data.get("production") != "NO_GO":
        return False
    for key in ["attempt_id", "obligation_id"]:
        if key in data and (not isinstance(data[key], str) or not ID.fullmatch(data[key])):
            return False
    if context.obligation_id and "obligation_id" in data and data["obligation_id"] != context.obligation_id:
        return False
    if context.attempt_id and "attempt_id" in data and data["attempt_id"] != context.attempt_id:
        return False
    for key in ["historical_decision", "redispatched", "ever_paid", "dispatch_intent_recorded"]:
        if key in data and type(data[key]) is not bool:
            return False
    if context.request_kind in {"create_attempt", "lookup_operation"} and data.get("historical_decision") is True and data.get("redispatched") is not False:
        return False
    for key in ["amount_minor", "maximum_source_debit_minor", "available_principal_minor", "approval_revision"]:
        if key in data and (type(data[key]) is not int or not 0 <= data[key] <= 9_007_199_254_740_991
                            or key == "approval_revision" and data[key] < 1):
            return False
    if "decision" in data and data["decision"] not in DECISIONS:
        return False
    if "state" in data and data["state"] not in STATES:
        return False
    if "execution_outcome" in data and data["execution_outcome"] not in STATES | {"UNKNOWN", "PREPARED_BLOCKED"}:
        return False
    if "reason" in data and not isinstance(data["reason"], str):
        return False
    def valid_attempt(attempt: Any) -> bool:
        return isinstance(attempt, dict) and isinstance(attempt.get("attempt_id"), str) and bool(ID.fullmatch(attempt["attempt_id"])) and isinstance(attempt.get("obligation_id"), str) and bool(ID.fullmatch(attempt["obligation_id"])) and (
            context.obligation_id is None or attempt["obligation_id"] == context.obligation_id) and attempt.get("state") in STATES and _valid_result(
                {**attempt, "mode": "local-evaluation", "production": "NO_GO"},
                RecoveryContext(context.api_origin, "attempt", "REPEAT_READ", "ATTEMPT_ID", attempt["attempt_id"],
                                context.request_fingerprint, attempt_id=attempt["attempt_id"]))
    kind = context.request_kind
    if kind == "approve_source":
        return data.get("decision") in {"REGISTERED", "REVOKED", "HOLD", "REFUSE"} and (
            data["decision"] not in {"REGISTERED", "REVOKED"} or isinstance(data.get("obligation_id"), str))
    if kind == "obligation":
        return data.get("obligation_id") == context.obligation_id and isinstance(data.get("attempts"), list) and all(valid_attempt(a) for a in data["attempts"])
    if kind == "attempt":
        return data.get("attempt_id") == context.attempt_id and data.get("state") in STATES
    if kind == "lookup_operation":
        if data.get("historical_decision") is not True or data.get("redispatched") is not False:
            return False
        nested = data.get("attempt")
        if data.get("attempt_id") is not None:
            if not valid_attempt(nested) or nested["attempt_id"] != data["attempt_id"]:
                return False
        return data.get("decision") in {"ACCEPT", "HOLD", "REFUSE"} and (data["decision"] != "ACCEPT" or "attempt_id" in data)
    if kind == "create_attempt":
        return data.get("decision") in {"ACCEPT", "HOLD", "REFUSE"} and (
            data["decision"] != "ACCEPT" or isinstance(data.get("attempt_id"), str) and "execution_outcome" in data)
    if kind in {"recover", "cancel", "resume"}:
        return data.get("decision") in {"HOLD", "REFUSE", "OBSERVED"} and (
            data["decision"] != "OBSERVED" or data.get("attempt_id") == context.attempt_id and data.get("state") in STATES)
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
        self.opener = build_opener(_NoRedirect)
        self.transport, self.on_event, self.closed = transport, on_event, False

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            if self.transport is not None:
                self.transport.close()

    def __enter__(self) -> Client:
        if self.closed:
            raise ValidationError("Client is closed")
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

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
        def failure(code: str) -> TransportError:
            cls = UncertainDispatch if method == "POST" else TransportError
            return cls(code, context, status=status, request_id=request_id)
        def consume(response: Any) -> PaymentResult:
            nonlocal status, request_id
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
            if status >= 400:
                code = parsed.get("error") if isinstance(parsed, dict) else None
                if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,128}", code):
                    raise failure("INVALID_ERROR_RESPONSE")
                raise APIError(code, status, recovery=context, request_id=request_id)
            if status != 200 or not _valid_result(parsed, context):
                raise failure("INVALID_RESPONSE_CONTRACT")
            return cast(PaymentResult, parsed)
        try:
            try:
                with (self.transport or self.opener).open(req, timeout=self.timeout) as response:
                    result = consume(response)
            except HTTPError as exc:
                with exc:
                    result = consume(exc)
            result_kind = "response"
            return result
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

    def approve_source(self, envelope: dict[str, Any] | str) -> PaymentResult:
        if isinstance(envelope, str):
            try:
                parsed = _strict_json(envelope)
            except (ValueError, RecursionError):
                raise ValidationError("Original signed source JSON required") from None
        else:
            parsed = envelope
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

    def lookup_operation(self, operation_id: str) -> PaymentResult:
        op = _identifier(operation_id)
        return self._request("GET", "/v1/payment-attempts/lookup?" + urlencode({"operation_id": op}), kind="lookup_operation", operation_id=op)

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
