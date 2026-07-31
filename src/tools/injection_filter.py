"""Filtre anti-injection Niveau 1 — Détection heuristique par regex.

Utilisé au moment du chunking (ingestion offline) pour marquer les chunks suspects.
Ne bloque pas l'ingestion — ajoute un score `injection_risk` aux métadonnées.
Le trust tier OKF (unverified/machine-confirmed/human-reviewed) gère la quarantaine.
"""
import re
from dataclasses import dataclass
from enum import StrEnum


class InjectionRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class InjectionRisk:
    risk: InjectionRiskLevel
    patterns_matched: list[str]
    confidence: float

    @property
    def flagged(self) -> bool:
        return self.risk in (InjectionRiskLevel.MEDIUM, InjectionRiskLevel.HIGH)


_PATTERNS_HIGH = [
    r"ignore\s+(?:all|the\s+)?\s*(?:previous|prior|above|any|prior\s+to\s+this)\s+instructions?",
    r"disregard\s+(?:all|the\s+)?\s*(?:previous|prior|above|any|prior\s+to\s+this)\s+instructions?",
    r"forget\s+(?:everything|all|any|everything\s+you\s+know)\s+(?:instructions?|context|what\s+you\s+know)",
    r"you\s+are\s+now\s+(?:a|an)\s+\w+",
    r"system\s+prompt",
    r"as\s+an\s+ai\s+(?:assistant|model)",
    r"pretend\s+to\s+be",
    r"roleplay\s+as",
    r"simulate\s+being",
    r"override\s+(?:safety|security|guidelines?)",
    r"bypass\s+(?:safety|security|filters?)",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"unrestricted\s+mode",
    r"you\s+are\s+(?:no\s+longer\s+)?\s*(?:not\s+)?\s*bound\s+by",
    r"ignore\s+(?:all\s+)?(?:ethical\s+|moral\s+)?(?:constraints?|guidelines?|rules?)",
]

_PATTERNS_MEDIUM = [
    r"important\s*:?\s*ignore",
    r"note\s*:?\s*disregard",
    r"please\s+ignore",
    r"don't\s+follow",
    r"do\s+not\s+follow",
    r"new\s+instructions?",
    r"updated\s+instructions?",
    r"secret\s+instructions?",
    r"hidden\s+instructions?",
]


_COMPILED_HIGH = [re.compile(p, re.IGNORECASE) for p in _PATTERNS_HIGH]
_COMPILED_MEDIUM = [re.compile(p, re.IGNORECASE) for p in _PATTERNS_MEDIUM]


def scan(text: str) -> InjectionRisk:
    """Analyse un texte et retourne le niveau de risque d'injection.

    Args:
        text: Texte à analyser (chunk, page, source brute)

    Returns:
        InjectionRisk avec risk level, patterns matchés, et confidence
    """
    if not text or not text.strip():
        return InjectionRisk(
            risk=InjectionRiskLevel.LOW,
            patterns_matched=[],
            confidence=1.0,
        )

    matched_high = []
    matched_medium = []

    for pattern in _COMPILED_HIGH:
        if pattern.search(text):
            matched_high.append(pattern.pattern)

    for pattern in _COMPILED_MEDIUM:
        if pattern.search(text):
            matched_medium.append(pattern.pattern)

    if matched_high:
        return InjectionRisk(
            risk=InjectionRiskLevel.HIGH,
            patterns_matched=matched_high,
            confidence=0.95,
        )

    if matched_medium:
        return InjectionRisk(
            risk=InjectionRiskLevel.MEDIUM,
            patterns_matched=matched_medium,
            confidence=0.75,
        )

    return InjectionRisk(
        risk=InjectionRiskLevel.LOW,
        patterns_matched=[],
        confidence=0.99,
    )


def scan_batch(texts: list[str]) -> list[InjectionRisk]:
    """Analyse une liste de textes (ex: chunks d'un document)."""
    return [scan(t) for t in texts]
