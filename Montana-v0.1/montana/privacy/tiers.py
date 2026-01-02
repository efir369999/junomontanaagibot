"""
Ɉ Montana Privacy Tiers v3.1

Privacy tier definitions per MONTANA_TECHNICAL_SPECIFICATION.md §14.

Tiers:
- T0: Transparent (sender, receiver, amount visible)
- T1: Hidden receiver (stealth address)
- T2: Hidden receiver + amount (Pedersen commitment)
- T3: Fully private (ring signature, size 11)
"""

from __future__ import annotations
from typing import Optional, Tuple

from montana.core.types import PrivacyTier, Hash, PublicKey
from montana.constants import (
    PRIVACY_T0,
    PRIVACY_T1,
    PRIVACY_T2,
    PRIVACY_T3,
    PRIVACY_FEE_MULTIPLIERS,
    RING_SIZE,
)


def get_fee_multiplier(tier: PrivacyTier) -> int:
    """
    Get fee multiplier for privacy tier.

    T0: 1x (transparent)
    T1: 2x (stealth)
    T2: 5x (stealth + Pedersen)
    T3: 10x (ring signature)
    """
    return PRIVACY_FEE_MULTIPLIERS.get(int(tier), 1)


def validate_privacy_tier(tier: int) -> Tuple[bool, Optional[str]]:
    """
    Validate privacy tier value.

    Returns:
        (is_valid, error_message)
    """
    if tier < PRIVACY_T0 or tier > PRIVACY_T3:
        return False, f"Invalid privacy tier: {tier}"
    return True, None


def get_tier_name(tier: PrivacyTier) -> str:
    """Get human-readable tier name."""
    names = {
        PrivacyTier.T0: "Transparent",
        PrivacyTier.T1: "Stealth",
        PrivacyTier.T2: "Confidential",
        PrivacyTier.T3: "Private",
    }
    return names.get(tier, "Unknown")


def get_tier_description(tier: PrivacyTier) -> str:
    """Get tier description."""
    descriptions = {
        PrivacyTier.T0: "Sender, receiver, and amount are visible",
        PrivacyTier.T1: "Receiver hidden via stealth address",
        PrivacyTier.T2: "Receiver and amount hidden via Pedersen commitment",
        PrivacyTier.T3: f"Fully private via ring signature (size {RING_SIZE})",
    }
    return descriptions.get(tier, "Unknown tier")
