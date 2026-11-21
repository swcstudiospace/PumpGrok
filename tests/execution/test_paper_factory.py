"""Paper factory builds adapters with the configured model (FEE-01)."""

from __future__ import annotations

from pumpgrok.config.sections.v4 import PaperFeesSettings
from pumpgrok.execution.fees import FeeModel, FeeModelV2
from pumpgrok.execution.paper_factory import paper_fees_from


def test_default_is_v2() -> None:
    fees = paper_fees_from(PaperFeesSettings())
    assert isinstance(fees, FeeModelV2)


def test_v1_selectable() -> None:
    fees = paper_fees_from(PaperFeesSettings(model="v1"))
    assert isinstance(fees, FeeModel)
    assert not isinstance(fees, FeeModelV2)
