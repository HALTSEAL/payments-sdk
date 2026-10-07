from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, ContextManager, Literal, Protocol, TypedDict
from urllib.request import Request

PaymentState = Literal["PREPARED", "EXPOSED", "PENDING", "IN_TRANSIT", "PAID", "CLOSED", "FAILED_REVIEW", "NEVER_DISPATCHED"]

class AttemptRecord(TypedDict):
    attempt_id: str
    obligation_id: str
    route: Literal["A", "B", "C"]
    product_instance_id: str
    state: PaymentState
    execution_outcome: PaymentState | Literal["UNKNOWN", "PREPARED_BLOCKED"]
    amount_minor: int
    approval_revision: int
    ever_paid: bool
    dispatch_intent_recorded: bool
    source_status: str | None
    original_payment_id: str | int | None
    source_evidence_digest: str | None
    closure_profile: str | None

class _Boundary(TypedDict):
    mode: Literal["local-evaluation"]
    production: Literal["NO_GO"]

class PaymentResult(_Boundary, total=False):
    decision: Literal["ACCEPT", "HOLD", "REFUSE", "REGISTERED", "REVOKED", "OBSERVED"]
    reason: str
    obligation_id: str
    operation_id: str
    attempt_id: str
    execution_outcome: PaymentState | Literal["UNKNOWN", "PREPARED_BLOCKED"]
    state: PaymentState
    historical_decision: bool
    redispatched: bool
    attempt: AttemptRecord
    attempts: list[AttemptRecord]
    available_principal_minor: int
    approval_revision: int
    approval_expires_at_ns: str
    approval_status: Literal["APPROVED", "REVOKED"]
    original_payment_id: str | int | None

@dataclass(frozen=True)
class RecoveryContext:
    api_origin: str
    request_kind: str
    action: Literal["LOOKUP_OPERATION", "LOOKUP_ATTEMPT", "REPEAT_READ", "REVIEW_SOURCE"]
    identity_kind: Literal["OPERATION_ID", "ATTEMPT_ID", "OBLIGATION_ID", "SOURCE_APPROVAL"]
    identity_value: str | None
    request_fingerprint: str
    operation_id: str | None = None
    obligation_id: str | None = None
    attempt_id: str | None = None
    approval_revision: int | None = None
    request_may_have_executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class Transport(Protocol):
    """One send, no redirects/internal retries; no financial IO on close.

    Return an urllib-compatible response context manager with status, headers,
    read(size) and geturl(). Custom TLS/proxy/pooling retain this contract.
    """
    def open(self, request: Request, *, timeout: float) -> ContextManager[Any]: ...
    def close(self) -> None: ...
