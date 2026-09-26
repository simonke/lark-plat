"""P6 AIOps automation leaf constants (served-tier probe target).

Pure constants only: this module must stay import-side-effect free (no router,
DB session, flag lookups) so the served-tier probe can import it in an isolated
subprocess and read the running symbols.

Frozen contract: @架构 P6 tuple r1 (seq3560 + notes r1.1-r1.7) + @需求 §30.
"""

from __future__ import annotations

# P6 migration revision id: single head descending directly from the P5 rev
# `f5a6b7c8d9e0`. Doubles as the served-tier "this build is P6" symbol (r1 D):
# `migration head == P6_REV` binds the code and migration versions to one source.
P6_REV = "P6_REV"

# Approval modes for `ApprovalRequest.approval_mode` / `ai_action.approval_mode`
# (r1 C①). Single source (leaf); the model columns are plain `String` and must
# not reference this tuple (no models -> services reverse dependency).
APPROVAL_MODES = ("auto_policy", "manual")

# r1.6: the only risk level eligible for L4 auto-approval (`auto_policy`). Named
# net-new constant in this leaf module; inline `"low"` literals are forbidden.
L4_AUTO_RISK_LEVELS = ("low",)
