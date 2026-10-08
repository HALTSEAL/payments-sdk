"""Connect your permitted nonproduction code here. Empty hooks never pass.

Copy this file outside the repository before editing. The reference adapter is
only a kit fixture; do not rename it and claim customer coverage.
"""

adapter_kind = "unconfigured"


class NotConfigured(RuntimeError):
    pass


def map_reference(context):
    """Return your stable shared transaction reference on BOTH software paths."""
    raise NotConfigured("Connect the shared transaction mapping")


def original(client, context):
    """Call your original execution point, routed through the unchanged SDK."""
    raise NotConfigured("Connect the original software execution point")


def replacement(client, context):
    """Call your replacement execution point, routed through the same SDK."""
    raise NotConfigured("Connect the replacement software execution point")


def recover(client, context):
    """Lookup the exact operation, or recover the retained attempt. No create."""
    raise NotConfigured("Connect exact-original recovery")


def stop(client, context, result):
    """Stop your application flow on HOLD/REFUSE. Never call another sender."""
    raise NotConfigured("Connect the application's stop branch")
