from app.ai.schemas import Issue


# Steps where the customer needs to check something or provide more details.
CUSTOMER_STEPS = {"valve-check", "ask-details"}


def resolve_issue(issue: Issue) -> str:
    """Choose the next step using the facts reported by the customer."""
    step = next_step(issue)
    if step not in CUSTOMER_STEPS | {"escalate"} and not issue.order_number:
        return "ask-details"
    return step


def next_step(issue: Issue) -> str:
    if issue.product == "paddle-board":
        if issue.problem == "missing-accessory":
            return "ship-part"
        if issue.problem == "slow-leak":
            if not issue.valve_checked:
                return "valve-check"
            if issue.days_since_delivery is None:
                return "ask-details"
            return "new-board" if issue.days_since_delivery <= 30 else "patch-kit"

    if issue.product == "shelving":
        if issue.problem == "missing-hardware":
            return "ship-hardware-kit"
        if issue.problem == "wrong-finish":
            return "exchange"
        if issue.problem == "damaged-frame":
            return "full-replacement"
        if issue.problem == "damaged-panels":
            if not issue.part_numbers:
                return "ask-details"
            return "ship-panels" if len(issue.part_numbers) <= 2 else "full-replacement"

    # A colleague handles split seams and any other unhandled issue.
    return "escalate"