"""Fixtures pytest — garantit un fonctionnement 100% offline.

tiktoken.get_encoding() télécharge les encodages BPE depuis
openaipublic.blob.core.windows.net au premier appel. Pour rester
fidèle à la philosophie "100% offline / mock-first" (CI sans accès
réseau), TIKTOKEN_CACHE_DIR pointe vers le fichier vendored dans
vendor/tiktoken/ (cl100k_base, hash sha1 de l'URL) — cf. src/__init__.py.
"""

import os
from pathlib import Path

_TIKTOKEN_VENDORED = Path(__file__).resolve().parent.parent / "vendor" / "tiktoken"
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(_TIKTOKEN_VENDORED))
