"""Paper factory: the only constructor path for paper adapters (FEE-01).

Builds the PaperAdapter with the configured FeeModel. Never imports
``pumpgrok.execution.live.*`` (the import-graph guard covers this module).
"""

from __future__ import annotations

from typing import Any

from pumpgrok.config.sections.v4 import PaperFeesSettings
from pumpgrok.execution.fees import FeeModel, fee_model_for
from pumpgrok.execution.paper_adapter import PaperAdapter


def paper_fees_from(settings: PaperFeesSettings) -> FeeModel:
    """The FeeModel selected by config; every existing v1 number is unchanged."""
    return fee_model_for(settings.model)


def build_paper_adapter(settings: PaperFeesSettings, **kwargs: Any) -> PaperAdapter:
    """Build a PaperAdapter with the configured model, forwarding the harness."""
    fees = paper_fees_from(settings)
    return PaperAdapter(fees=fees, **kwargs)
