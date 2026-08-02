"""Cluster RAG Multi-Agents 100% Offline."""

import os
from pathlib import Path

_TIKTOKEN_CACHE = (Path(__file__).resolve().parent.parent / "vendor" / "tiktoken").resolve()
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(_TIKTOKEN_CACHE))
