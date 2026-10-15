"""Métriques : comparer la décision de chaque exécution à la vérité terrain, puis agréger."""

import json
from collections import Counter
from dataclasses import asdict, dataclass

from aml_agents.decision import Decision, Donnees
from aml_agents.outils import DONNEES
from aml_agents.schema import Rapport


@dataclass(frozen=True)
class Mesure:
    """Résultat d'une exécution sur une alerte."""

    alerte_id: str
    verdict: str  # vrai_positif | faux_positif
    issue: str
    score: int
    signaux_valides: tuple[str, ...]  # signaux retenus après vérification par le code
    rappel_signaux: (
        float | None
    )  # part des signaux attendus retrouvés (None si aucun attendu)
    constats_emis: int
    constats_invalides: int  # écartés par decision.py
    preuves_inexistantes: int  # identifiants de transactions inventés
    faux_negatif: bool  # vrai positif classé sans suite
    faux_positif: bool  # faux positif non classé sans suite


def charger_verite() -> dict:
    return json.loads((DONNEES / "verite.json").read_text(encoding="utf-8"))["alertes"]


def mesurer(
    decision: Decision, rapport: Rapport, verite_alerte: dict, donnees: Donnees
) -> Mesure:
    attendus = set(verite_alerte["signaux_attendus"])
    valides = {v.constat.signal for v in decision.constats_verifies if v.valide}
    rappel = len(valides & attendus) / len(attendus) if attendus else None
    inventees = sum(
        1
        for c in rapport.constats
        for p in dict.fromkeys(c.preuves)
        if p not in donnees.transactions
    )
    classe_sans_suite = decision.issue == "classer_sans_suite"
    vrai_positif = verite_alerte["verdict"] == "vrai_positif"
    return Mesure(
        alerte_id=decision.alerte_id,
        verdict=verite_alerte["verdict"],
        issue=decision.issue,
        score=decision.score,
        signaux_valides=tuple(sorted(valides)),
        rappel_signaux=rappel,
        constats_emis=len(rapport.constats),
        constats_invalides=len(decision.constats_invalides),
        preuves_inexistantes=inventees,
        faux_negatif=vrai_positif and classe_sans_suite,
        faux_positif=not vrai_positif and not classe_sans_suite,
    )


def _moyenne(valeurs: list[float]) -> float | None:
    return round(sum(valeurs) / len(valeurs), 3) if valeurs else None


def agreger(mesures: list[Mesure], echecs: int = 0) -> dict:
    """Résumé de N exécutions de la même alerte. `echecs` : exécutions qui ont planté (hors mesures)."""
    n = len(mesures)
    return {
        "executions_reussies": n,
        "executions_echouees": echecs,
        "issues": dict(Counter(m.issue for m in mesures)),
        "score_moyen": _moyenne([m.score for m in mesures]),
        "rappel_moyen": _moyenne(
            [m.rappel_signaux for m in mesures if m.rappel_signaux is not None]
        ),
        "faux_negatifs": sum(m.faux_negatif for m in mesures),
        "faux_positifs": sum(m.faux_positif for m in mesures),
        "constats_emis": sum(m.constats_emis for m in mesures),
        "constats_invalides": sum(m.constats_invalides for m in mesures),
        "preuves_inexistantes": sum(m.preuves_inexistantes for m in mesures),
    }


def en_dict(mesure: Mesure) -> dict:
    return asdict(mesure)
