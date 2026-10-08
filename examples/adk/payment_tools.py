"""Host-bound ADK tools. No payment authority is derived from model arguments.

This example's operation journal and stop latch live in memory outside ADK.
A real integration must persist intent before IO and authorize every binding
in its trusted application, backed by its separately qualified evaluator.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from google.adk.tools import FunctionTool
from haltseal_payments_sdk import APIError, Client, TransportError, ValidationError


@dataclass(frozen=True)
class PaymentBinding:
    """Trusted host input, never an LLM/session/task-derived approval."""

    obligation_id: str
    operation_id: str
    route: Literal["A", "B", "C"]
    approval_revision: int


@dataclass
class OperationJournal:
    """Host-retained submission intent; rehydrate before reconstructing tools."""

    binding: PaymentBinding
    submitted: bool = False
    lock: Lock = field(default_factory=Lock, repr=False)


@dataclass
class PaymentControls:
    """Local application stop scope shared by the tools the host gives it."""

    stopped: bool = False
    lock: Lock = field(default_factory=Lock, repr=False)


class BoundPaymentTools:
    def __init__(self, client: Client, journal: OperationJournal,
                 controls: PaymentControls):
        self._client, self._journal, self._controls = client, journal, controls

    def _hold(self, reason: str, *, sdk_request_sent: bool = False) -> dict:
        binding = self._journal.binding
        return {"mode": "local-evaluation", "production": "NO_GO",
                "decision": "HOLD", "reason": reason, "decision_source": "adapter",
                "obligation_id": binding.obligation_id,
                "operation_id": binding.operation_id,
                "sdk_request_sent": sdk_request_sent,
                "next_action": "LOOKUP_BOUND_OPERATION_OR_OWNER_REVIEW"}

    def _submit(self) -> dict:
        with self._controls.lock, self._journal.lock:
            if self._controls.stopped:
                return self._hold("LOCAL_PAYMENT_REQUESTS_STOPPED")
            if self._journal.submitted:
                return self._hold("OPERATION_ALREADY_SUBMITTED_USE_LOOKUP")
            # Fail closed even if the reply is lost or the coroutine is cancelled.
            # Production intent persistence must happen here, before network IO.
            self._journal.submitted = True
            binding = self._journal.binding
            try:
                result = self._client.create_attempt(
                    binding.obligation_id, operation_id=binding.operation_id,
                    route=binding.route, approval_revision=binding.approval_revision)
            except (TransportError, APIError):
                return self._hold("SUBMISSION_REPLY_UNAVAILABLE_OR_REJECTED",
                                  sdk_request_sent=True)
            except ValidationError:
                return self._hold("LOCAL_INPUT_REQUIRES_OWNER_REVIEW")
            return {**result, "decision_source": "sdk", "sdk_request_sent": True}

    async def request_payment(self) -> dict:
        """Request the host-bound attempt once. HOLD/REFUSE block any new send.

        No identity, route, amount, approval or closure is accepted from the model.
        Repeated calls require exact-operation lookup; ACCEPT is not settlement.
        """
        return await asyncio.to_thread(self._submit)

    def _lookup(self) -> dict:
        binding = self._journal.binding
        try:
            result = self._client.lookup_operation(
                binding.operation_id, obligation_id=binding.obligation_id)
        except (TransportError, APIError):
            # Includes 404: no record found is not evidence of no financial effect.
            return self._hold("ORIGINAL_LOOKUP_UNAVAILABLE_OR_NOT_FOUND",
                              sdk_request_sent=True)
        except ValidationError:
            return self._hold("LOCAL_INPUT_REQUIRES_OWNER_REVIEW")
        return {**result, "decision_source": "sdk", "sdk_request_sent": True}

    async def lookup_payment(self) -> dict:
        """Read only the bound operation. Historical ACCEPT grants no new send.

        Read recovery remains available after the local stop. Missing replies,
        lookup 404 and agent claims never establish authoritative closure.
        """
        return await asyncio.to_thread(self._lookup)

    def _stop(self) -> dict:
        # After this returns, later requests in this shared local scope cannot
        # enter create_attempt. Already submitted requests can still take effect.
        with self._controls.lock:
            self._controls.stopped = True
        return self._hold("LOCAL_PAYMENT_REQUESTS_STOPPED")

    async def stop_payment_requests(self) -> dict:
        """Stop later submissions in this local scope; preserve original identity.

        This is neither provider cancellation nor authoritative closure. It does
        not restore money or reset the submitted journal. Read recovery is allowed.
        """
        return await asyncio.to_thread(self._stop)

    def tools(self) -> list[FunctionTool]:
        return [FunctionTool(self.request_payment), FunctionTool(self.lookup_payment),
                FunctionTool(self.stop_payment_requests)]
