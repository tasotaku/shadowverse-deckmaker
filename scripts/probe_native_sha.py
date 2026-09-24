"""Development probe: pass Python's existing SHA256 implementation to compiled code."""
import ctypes
import hashlib
import sys
from pathlib import Path
import numpy as np
from numba import njit

library = ctypes.CDLL(str(Path(sys.base_prefix)/'DLLs/libcrypto-3.dll'))
sha = library.SHA256
sha.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
sha.restype = ctypes.c_void_p


@njit(cache=True)
def call(data, output, function):
    # AI_NOTE: Function address is a runtime argument, never an address embedded in a persistent JIT cache.
    function(data.ctypes, len(data), output.ctypes)


for raw in (b'', b'abc', b'x'*1000):
    data = np.frombuffer(raw, dtype=np.uint8)
    output = np.empty(32, dtype=np.uint8)
    call(data, output, sha)
    assert output.tobytes() == hashlib.sha256(raw).digest()
print('PASS dynamic SHA256 pointer')
