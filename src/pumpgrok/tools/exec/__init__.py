"""Paper-write execution tools (TOOL-004, Phase 3 input-contract scope).

``exec.place`` and ``exec.cancel`` validate the catalog input contract
fail-closed (approval required, decision key, side/size match, exit cannot
BUY) and delegate to the injected :class:`ExecutionAdapter`. In Phase 3 the
adapter is :class:`NotYetImplementedAdapter`: every method raises
``not_yet_implemented`` instead of faking fills (bindings B5, B7).
"""

from __future__ import annotations
