"""Operator onboarding family ONB-01..ONB-10 (Phase 14).

Input inventory, doctor readiness, paper start gate, seat access approval,
no-secret-echo guarantee, wallet/RPC validation, x.ai key rules, and the
live HMAC prohibition. Secret values never reach reports; reports carry
presence and source only.
"""

from pumpgrok.config.sections.onboarding import OnboardingSettings
from pumpgrok.onboarding.access import has_access, record_access
from pumpgrok.onboarding.choices import read_choices, record_choice
from pumpgrok.onboarding.doctor_report import InputRecord, doctor_records
from pumpgrok.onboarding.inventory import INVENTORY, InputSpec, inventory_snapshot_hash
from pumpgrok.onboarding.start_gate import check_start
from pumpgrok.onboarding.validators import (
    host_only,
    is_valid_wallet_address,
    refuse_wallet,
)

__all__ = [
    "INVENTORY",
    "InputRecord",
    "InputSpec",
    "OnboardingSettings",
    "check_start",
    "doctor_records",
    "has_access",
    "host_only",
    "inventory_snapshot_hash",
    "is_valid_wallet_address",
    "read_choices",
    "record_access",
    "record_choice",
    "refuse_wallet",
]
