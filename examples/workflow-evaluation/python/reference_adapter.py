"""Synthetic kit wiring only. This is not customer installation evidence."""

adapter_kind = "reference-fixture"


def map_reference(context):
    return context["business_reference"]


def original(client, context):
    return client.create_attempt(
        context["obligation_id"], operation_id=context["operation_id"],
        route="A", approval_revision=context["approval_revision"],
    )


def replacement(client, context):
    return client.create_attempt(
        context["obligation_id"], operation_id=context["operation_id"],
        route="B", approval_revision=context["approval_revision"],
    )


def recover(client, context):
    if context["recovery_action"] == "LOOKUP_OPERATION":
        return client.lookup_operation(context["operation_id"],
                                       obligation_id=context["obligation_id"])
    return client.recover(context["attempt_id"])


def stop(client, context, result):
    if result["decision"] not in {"HOLD", "REFUSE"}:
        raise ValueError("The stop hook only handles a blocked execution")
    return "STOP"
