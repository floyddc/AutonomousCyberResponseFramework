import math
from typing import Any, Dict, List, Optional


def requires_human_approval(
    severity: Optional[str],
    confidence: Any,
    severity_order: List[str],
    approval_ceiling: str,
    confidence_thresholds: Dict[str, Any],
) -> bool:
    if severity not in severity_order:
        return True
    severity_rank = severity_order.index(severity)
    if severity_rank >= severity_order.index(approval_ceiling):
        return True

    threshold = confidence_thresholds[severity]
    return (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or confidence < 0
        or confidence > 1
        or not math.isfinite(confidence)
        or confidence < threshold
    )
