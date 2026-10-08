"""ADK boundary guards. Recording-client checks are not payment-engine proof."""
import asyncio
from pathlib import Path
import sys
from threading import Event
import unittest

from haltseal_payments_sdk import APIError, RecoveryContext, TransportError, UncertainDispatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples/adk"))
from payment_tools import BoundPaymentTools, OperationJournal, PaymentBinding, PaymentControls
from scripted_agent import run_tools


class RecordingClient:
    def __init__(self):
        self.creates, self.lookups = [], []
        self.create_error = self.lookup_error = None
        self.entered = self.release = None

    def create_attempt(self, obligation_id, **kwargs):
        self.creates.append({"obligation_id": obligation_id, **kwargs})
        if self.entered is not None:
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("Test did not release the pending call")
        if self.create_error:
            raise self.create_error
        return {"mode": "local-evaluation", "production": "NO_GO", "decision": "ACCEPT",
                "obligation_id": obligation_id, "operation_id": kwargs["operation_id"],
                "execution_outcome": "UNKNOWN"}

    def lookup_operation(self, operation_id, *, obligation_id):
        self.lookups.append((operation_id, obligation_id))
        if self.lookup_error:
            raise self.lookup_error
        return {"mode": "local-evaluation", "production": "NO_GO", "decision": "ACCEPT",
                "obligation_id": obligation_id, "operation_id": operation_id,
                "execution_outcome": "UNKNOWN", "historical_decision": True, "redispatched": False}


def uncertain(error_type=UncertainDispatch):
    return error_type("HTTP_503", RecoveryContext(
        "http://127.0.0.1:8799", "create_attempt", "LOOKUP_OPERATION", "OPERATION_ID",
        "retained-operation", "0" * 64, operation_id="retained-operation",
        obligation_id="retained-obligation", approval_revision=1, request_may_have_executed=True))


class ADKToolGuards(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = RecordingClient()
        self.binding = PaymentBinding("retained-obligation", "retained-operation", "B", 1)
        self.journal, self.controls = OperationJournal(self.binding), PaymentControls()
        self.adapter = BoundPaymentTools(self.client, self.journal, self.controls)

    async def test_uncertain_reply_never_resends_on_repeat(self):
        self.client.create_error = uncertain()
        first = await self.adapter.request_payment()
        repeated = await self.adapter.request_payment()
        recovered = await self.adapter.lookup_payment()
        self.assertEqual(first["decision"], "HOLD")
        self.assertFalse(repeated["sdk_request_sent"])
        self.assertTrue(recovered["historical_decision"])
        self.assertFalse(recovered["redispatched"])
        self.assertEqual(len(self.client.creates), 1)
        self.assertEqual(self.client.lookups, [("retained-operation", "retained-obligation")])

    async def test_lookup_404_keeps_submission_reserved(self):
        self.client.create_error = uncertain()
        self.client.lookup_error = APIError("OPERATION_NOT_FOUND", 404)
        await self.adapter.request_payment()
        missing = await self.adapter.lookup_payment()
        repeated = await self.adapter.request_payment()
        self.assertEqual(missing["decision"], "HOLD")
        self.assertTrue(self.journal.submitted)
        self.assertFalse(repeated["sdk_request_sent"])
        self.assertEqual(len(self.client.creates), 1)

    async def test_unavailable_lookup_keeps_original_binding(self):
        self.journal.submitted = True
        self.client.lookup_error = uncertain(TransportError)
        result = await self.adapter.lookup_payment()
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["operation_id"], "retained-operation")
        self.assertEqual(self.client.creates, [])
        self.assertTrue(self.journal.submitted)

    async def test_reconstructed_tools_use_host_submission_intent(self):
        restored = BoundPaymentTools(self.client, OperationJournal(self.binding, submitted=True),
                                     PaymentControls())
        result = await restored.request_payment()
        await restored.lookup_payment()
        self.assertFalse(result["sdk_request_sent"])
        self.assertEqual(self.client.creates, [])
        self.assertEqual(self.client.lookups, [("retained-operation", "retained-obligation")])

    async def test_stop_blocks_shared_scope_but_allows_original_read(self):
        self.client.create_error = uncertain()
        await self.adapter.request_payment()
        unused = OperationJournal(PaymentBinding("retained-obligation", "replacement", "C", 2))
        backup = BoundPaymentTools(self.client, unused, self.controls)
        await backup.stop_payment_requests()
        for tools in [self.adapter, backup]:
            result = await tools.request_payment()
            self.assertEqual(result["reason"], "LOCAL_PAYMENT_REQUESTS_STOPPED")
            self.assertFalse(result["sdk_request_sent"])
        read = await self.adapter.lookup_payment()
        self.assertEqual(read["execution_outcome"], "UNKNOWN")
        self.assertTrue(self.journal.submitted)
        self.assertFalse(unused.submitted)
        self.assertEqual(len(self.client.creates), 1)

    async def test_parallel_tools_sharing_journal_submit_once(self):
        other = BoundPaymentTools(self.client, self.journal, PaymentControls())
        results = await asyncio.gather(self.adapter.request_payment(), other.request_payment())
        self.assertEqual(sorted(result["decision"] for result in results), ["ACCEPT", "HOLD"])
        self.assertEqual(len(self.client.creates), 1)

    async def test_cancellation_does_not_reset_intent(self):
        self.client.entered, self.client.release = Event(), Event()
        task = asyncio.create_task(self.adapter.request_payment())
        try:
            self.assertTrue(await asyncio.to_thread(self.client.entered.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(self.journal.submitted)
        finally:
            self.client.release.set()
        repeated = await self.adapter.request_payment()
        self.assertFalse(repeated["sdk_request_sent"])
        self.assertEqual(len(self.client.creates), 1)

    async def test_real_adk_arguments_cannot_replace_host_authority(self):
        result = await run_tools(self.adapter, [{"tool": "request_payment", "args": {
            "obligation_id": "untrusted", "operation_id": "new-operation", "route": "C",
            "approval_revision": 999, "amount_minor": 999999, "original_is_closed": True}}],
            agent_name="argument_override_agent", session_id="untrusted-session-id")
        self.assertEqual(result["tool_results"][0]["result"]["decision"], "ACCEPT")
        self.assertEqual(self.client.creates, [{"obligation_id": "retained-obligation",
                         "operation_id": "retained-operation", "route": "B", "approval_revision": 1}])
        self.assertEqual([tool.name for tool in self.adapter.tools()],
                         ["request_payment", "lookup_payment", "stop_payment_requests"])


if __name__ == "__main__":
    unittest.main()
