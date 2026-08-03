"""Fixtures pytest — garantit un fonctionnement 100% offline.

tiktoken.get_encoding() télécharge les encodages BPE depuis
openaipublic.blob.core.windows.net au premier appel. Pour rester
fidèle à la philosophie "100% offline / mock-first" (CI sans accès
réseau), TIKTOKEN_CACHE_DIR pointe vers le fichier vendored dans
vendor/tiktoken/ (cl100k_base, hash sha1 de l'URL) — cf. src/__init__.py.
"""

import os
from pathlib import Path


class VendoredCacheMissingError(RuntimeError):
    """Cache tiktoken vendored introuvable — tests 100% offline impossibles.

    Sans le fichier BPE (cl100k_base), tiktoken tente un téléchargement
    réseau (échec opaque, HTTP 403 en CI offline) et 43 tests échouent sans
    explication. Message porté ici pour TRY003.
    """

    def __init__(self, expected: Path, cache_dir: Path) -> None:
        super().__init__(
            f"Cache tiktoken vendored absent : '{expected}'\n"
            "Sans lui, tiktoken tente un téléchargement réseau (échec opaque, 403, "
            "en CI offline) et 43 tests échouent sans explication.\n"
            "Régénérer le fichier une fois avec accès réseau :\n"
            f"  python -c \"import os; os.environ['TIKTOKEN_CACHE_DIR']=r'{cache_dir}'; "
            "import tiktoken; tiktoken.get_encoding('cl100k_base')\""
        )


_TIKTOKEN_VENDORED = Path(__file__).resolve().parent.parent / "vendor" / "tiktoken"
_TIKTOKEN_FILE = _TIKTOKEN_VENDORED / "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(_TIKTOKEN_VENDORED))

if not _TIKTOKEN_FILE.is_file():
    raise VendoredCacheMissingError(_TIKTOKEN_FILE, _TIKTOKEN_VENDORED)
