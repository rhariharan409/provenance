from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Tuple


def normalize_signal(raw_values: Dict[str, float]) -> Dict[str, float]:
    """
    Normalizes a dictionary of member_id -> raw_value to shares summing to 1.0 (0..1).
    If total is 0, all shares are 0.0.
    """
    total = sum(raw_values.values())
    if total > 0:
        return {m_id: val / total for m_id, val in raw_values.items()}
    return {m_id: 0.0 for m_id in raw_values.keys()}


def calculate_final_scores(
    member_ids: List[str],
    raw_survival: Dict[str, float],
    raw_effective_change: Dict[str, float],
    raw_ownership: Dict[str, float],
    raw_collaboration: Dict[str, float],
    weights: Dict[str, float],
    has_collaboration_data: bool,
) -> Tuple[Dict[str, Decimal], Dict[str, Dict[str, Any]], Dict[str, float]]:
    """
    Combines signals into final percentage scores summing to exactly 100.00.
    Returns:
      (final_percentages, per_member_signals, effective_weights)
    """
    if not member_ids:
        return {}, {}, weights

    eff_weights = dict(weights)

    # If no collaboration data, set collaboration weight to 0 and renormalize remaining
    if not has_collaboration_data:
        eff_weights["collaboration"] = 0.0
        rem_sum = (
            eff_weights.get("survival", 0.0)
            + eff_weights.get("effective_change", 0.0)
            + eff_weights.get("ownership", 0.0)
        )
        if rem_sum > 0:
            eff_weights["survival"] = eff_weights.get("survival", 0.0) / rem_sum
            eff_weights["effective_change"] = eff_weights.get("effective_change", 0.0) / rem_sum
            eff_weights["ownership"] = eff_weights.get("ownership", 0.0) / rem_sum

    norm_survival = normalize_signal(raw_survival)
    norm_effective = normalize_signal(raw_effective_change)
    norm_ownership = normalize_signal(raw_ownership)
    norm_collaboration = normalize_signal(raw_collaboration)

    # Compute raw share
    raw_shares: Dict[str, float] = {}
    for m_id in member_ids:
        s = (
            eff_weights.get("survival", 0.0) * norm_survival.get(m_id, 0.0)
            + eff_weights.get("effective_change", 0.0) * norm_effective.get(m_id, 0.0)
            + eff_weights.get("ownership", 0.0) * norm_ownership.get(m_id, 0.0)
            + eff_weights.get("collaboration", 0.0) * norm_collaboration.get(m_id, 0.0)
        )
        raw_shares[m_id] = s

    total_shares = sum(raw_shares.values())
    if total_shares == 0:
        # Equal distribution if all signals are 0
        equal_share = 1.0 / len(member_ids)
        raw_shares = {m_id: equal_share for m_id in member_ids}
    else:
        # Re-normalize in case some signals had 0 sum
        raw_shares = {m_id: val / total_shares for m_id, val in raw_shares.items()}

    # Convert to Decimal percentages and fix rounding to ensure exact 100.00
    percentages: Dict[str, Decimal] = {}
    for m_id, share in raw_shares.items():
        dec_val = Decimal(str(share * 100.0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        percentages[m_id] = dec_val

    current_sum = sum(percentages.values())
    target_sum = Decimal("100.00")
    diff = target_sum - current_sum

    if diff != Decimal("0.00"):
        # Adjust the member with the largest share
        largest_member = max(member_ids, key=lambda m: percentages[m])
        percentages[largest_member] += diff

    # Build per-member signals for explainability
    per_member_signals: Dict[str, Dict[str, Any]] = {}
    for m_id in member_ids:
        per_member_signals[m_id] = {
            "survival": {
                "raw": raw_survival.get(m_id, 0.0),
                "normalized": round(norm_survival.get(m_id, 0.0), 4),
                "weight": round(eff_weights.get("survival", 0.0), 4),
            },
            "effective_change": {
                "raw": raw_effective_change.get(m_id, 0.0),
                "normalized": round(norm_effective.get(m_id, 0.0), 4),
                "weight": round(eff_weights.get("effective_change", 0.0), 4),
            },
            "ownership": {
                "raw": raw_ownership.get(m_id, 0.0),
                "normalized": round(norm_ownership.get(m_id, 0.0), 4),
                "weight": round(eff_weights.get("ownership", 0.0), 4),
            },
            "collaboration": {
                "raw": raw_collaboration.get(m_id, 0.0),
                "normalized": round(norm_collaboration.get(m_id, 0.0), 4),
                "weight": round(eff_weights.get("collaboration", 0.0), 4),
            },
        }

    return percentages, per_member_signals, eff_weights

