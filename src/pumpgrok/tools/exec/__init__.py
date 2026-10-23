"""Paper-write execution tools (TOOL-004, Phase 3 input-contract scope).

``exec.place`` and ``exec.cancel`` validate the catalog input contract
fail-closed (approval required, decision key, side/size match, exit cannot
BUY) and delegate to the injected :class:`ExecutionAdapter`. The paper desk
injects :class:`PaperAdapter` (bindings B5, B7).
"""

from __future__ import annotations
