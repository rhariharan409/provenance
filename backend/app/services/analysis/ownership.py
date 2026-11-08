from typing import Any, Dict, List, Tuple


def compute_module_ownership(
    module_totals: Dict[str, int],
    member_module_lines: Dict[str, Dict[str, int]],
    total_surviving_lines: int,
    min_module_lines: int = 20,
) -> Tuple[Dict[str, float], Dict[str, List[Dict[str, Any]]]]:
    """
    Computes module ownership and the ownership signal per member.
    - Modules with >= min_module_lines lines have an owner (member with highest share).
    - Owned modules per member are recorded as: [{"path": m, "share": float}]
    - Ownership signal = sum over owned modules of (member_share * module_lines) / total_surviving_lines
    Returns:
      (member_ownership_signals, member_owned_modules)
    """
    member_ownership_signals: Dict[str, float] = {m_id: 0.0 for m_id in member_module_lines.keys()}
    member_owned_modules: Dict[str, List[Dict[str, Any]]] = {m_id: [] for m_id in member_module_lines.keys()}

    if total_surviving_lines <= 0:
        return member_ownership_signals, member_owned_modules

    for module_name, mod_total in module_totals.items():
        if mod_total < min_module_lines:
            continue

        best_member = None
        best_lines = 0

        for member_id, mod_dict in member_module_lines.items():
            lines = mod_dict.get(module_name, 0)
            if lines > best_lines:
                best_lines = lines
                best_member = member_id

        if best_member is not None and best_lines > 0:
            share = best_lines / mod_total
            member_owned_modules[best_member].append({
                "path": module_name,
                "share": round(share, 4),
            })
            effective_owned_lines = share * mod_total
            member_ownership_signals[best_member] += effective_owned_lines / total_surviving_lines

    return member_ownership_signals, member_owned_modules
