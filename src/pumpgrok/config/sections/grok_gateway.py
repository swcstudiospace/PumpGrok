"""Gateway settings section (Phase 14, grok_gateway).

Re-exports the composed `GrokGatewaySettings` class from config/sections/v4.py
so the gateway reads its gate from one place. The section defaults off.
"""

from __future__ import annotations

from pumpgrok.config.sections.v4 import GrokGatewaySettings

__all__ = ["GrokGatewaySettings"]
