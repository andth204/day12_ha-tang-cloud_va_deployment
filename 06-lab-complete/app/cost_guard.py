"""Per-user monthly cost guard — stops requests when monthly budget is exhausted."""
from datetime import datetime

from fastapi import HTTPException

from app.config import settings

# GPT-4o-mini pricing (per 1K tokens)
_INPUT_COST_PER_1K = 0.00015
_OUTPUT_COST_PER_1K = 0.0006

# {"{user_id}:{YYYY-MM}": cost_usd}
_monthly_cost: dict[str, float] = {}


def check_and_record_cost(user_id: str, input_tokens: int, output_tokens: int) -> None:
    """
    Per-user monthly budget check:
    1. Key = "{user_id}:{YYYY-MM}" → resets automatically each new month.
    2. Raises HTTP 402 if adding this request exceeds monthly_budget_usd.
    3. Records the cost after the check passes.
    """
    month_key = f"{user_id}:{datetime.now().strftime('%Y-%m')}"
    current = _monthly_cost.get(month_key, 0.0)

    if current >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly budget of ${settings.monthly_budget_usd} exceeded. Resets next month.",
        )

    cost = (input_tokens / 1000) * _INPUT_COST_PER_1K + \
           (output_tokens / 1000) * _OUTPUT_COST_PER_1K
    _monthly_cost[month_key] = current + cost
