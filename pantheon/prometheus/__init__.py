"""PROMETHEUS - God of Cryptography. Ed25519, ECVRF, Post-Quantum."""
from .crypto import *

# Crypto Agility Layer
from .crypto_provider import (
    CryptoProvider,
    CryptoBackend,
    VDFProofBase,
    SignatureBundle,
    LegacyCryptoProvider,
    get_crypto_provider,
    set_default_backend,
    get_default_backend,
    clear_provider_cache,
)

# Post-Quantum Cryptography
from .pq_crypto import (
    sha3_256,
    sha3_256d,
    sha3_512,
    shake256,
    hmac_sha3_256,
    SHAKE256VDF,
    STARKProver,
    PostQuantumCryptoProvider,
    HybridCryptoProvider,
    LIBOQS_AVAILABLE,
    MLKEM_AVAILABLE,
    WINTERFELL_AVAILABLE,
)
