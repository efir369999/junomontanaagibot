"""
Montana Cryptographic Primitives

Post-quantum secure cryptography per ATC Layer 0.
- SHA3-256, SHAKE256 (NIST FIPS 202)
- SPHINCS+-SHAKE-128f (NIST FIPS 205)
- ML-KEM-768 (NIST FIPS 203) [future]
"""

from montana.crypto.hash import (
    sha3_256,
    sha3_256_raw,
    shake256,
    shake256_hash,
    tagged_hash,
    double_sha3_256,
    HashBuilder,
    SHAKE256Builder,
)

from montana.crypto.sphincs import (
    sphincs_keygen,
    sphincs_sign,
    sphincs_verify,
    is_liboqs_available,
    SPHINCSPlus,
)

__all__ = [
    # Hash functions
    "sha3_256",
    "sha3_256_raw",
    "shake256",
    "shake256_hash",
    "tagged_hash",
    "double_sha3_256",
    "HashBuilder",
    "SHAKE256Builder",
    # SPHINCS+
    "sphincs_keygen",
    "sphincs_sign",
    "sphincs_verify",
    "is_liboqs_available",
    "SPHINCSPlus",
]
