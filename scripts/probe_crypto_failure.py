"""Isolated OpenSSL provider failure reproduction; never alters host configuration."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys

from svdeck.battle.battle import Battle
from svdeck.battle.battle_frontier_native import enumerate_native
from svdeck.battle.battle_frontier_export import materialize
from svdeck.battle.battle_frontier_export_native import sha256_provider


def main() -> None:
    # AI_NOTE: The caller supplies a process-only OPENSSL_CONF; verify NULL from the actual DLL and exact Python fallback.
    library = ctypes.CDLL(str(Path(sys.base_prefix)/'DLLs/libcrypto-3.dll'))
    function = library.SHA256
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    function.restype = ctypes.c_void_p
    sample, digest = ctypes.create_string_buffer(b'abc'), ctypes.create_string_buffer(32)
    address = function(sample, 3, digest)
    assert address is None, 'This process did not reproduce the configured crypto failure'
    assert sha256_provider() is None
    case = json.loads(Path('docs/evidence/turn-search-compare/independent-small-cases.v1.json').read_text(encoding='utf-8'))[0]
    search = enumerate_native(Battle(case['state'], case['cards']), max_states=100000, seconds=60)
    assert search.complete
    candidates = list(range(len(search.keys)))
    assert materialize(search, candidates) == materialize(search, candidates, backend='python')
    result = {'OPENSSL_CONF': os.environ['OPENSSL_CONF'], 'actual_SHA256_return': address,
              'hashlib_sha256_abc': hashlib.sha256(b'abc').hexdigest(), 'native_provider_rejected': True,
              'all_rows_and_hashes_equal_python': True, 'states': len(search.keys)}
    print(json.dumps(result, indent=2))
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
