"""Les trois outils par lesquels les agents lisent les données."""

import json
from datetime import date, timedelta
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain_core.tools import ToolException, tool

DONNEES = Path(__file__).resolve().parents[2] / "data"
DATE_REFERENCE = date(2026, 9, 30)
MAX_LIGNES = 100  # borne la taille des réponses


@lru_cache
def _charger(nom: str) -> list[dict]:
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


def _client(client_id: str) -> dict:
    for c in _charger("clients.json"):
        if c["id"] == client_id:
            return c
    raise ToolException(
        f"Client inconnu : {client_id!r}. Les identifiants ont la forme 'CLI-001'."
    )


@tool
def historique_client(
    client_id: str,
    jours: int = 730,
    mode: Literal["virement", "prelevement", "carte", "especes"] | None = None,
    sens: Literal["credit", "debit"] | None = None,
) -> dict:
    """Liste les transactions bancaires d'un client sur les `jours` derniers jours (jusqu'à la date de revue).

    Utilise `mode` et `sens` pour cibler (ex. mode='especes' pour les retraits d'espèces,
    sens='credit' pour les sommes reçues) : sans filtre, la réponse est volumineuse.
    La réponse donne le nombre et le montant total des transactions trouvées (calculés, fiables),
    puis les transactions les plus récentes avec leur identifiant (ex. TX-000123), à citer comme preuves.
    Si `tronque` est vrai, des transactions plus anciennes manquent : réduis `jours` ou ajoute un filtre.
    """
    _client(client_id)
    if jours < 1:
        raise ToolException("`jours` doit être supérieur ou égal à 1.")
    debut = DATE_REFERENCE - timedelta(days=jours - 1)
    trouvees = [
        t
        for t in _charger("transactions.json")
        if t["client_id"] == client_id
        and debut <= date.fromisoformat(t["date"]) <= DATE_REFERENCE
        and (mode is None or t["mode"] == mode)
        and (sens is None or t["sens"] == sens)
    ]
    trouvees.sort(key=lambda t: (t["date"], t["id"]), reverse=True)
    return {
        "client_id": client_id,
        "du": debut.isoformat(),
        "au": DATE_REFERENCE.isoformat(),
        "nombre_transactions": len(trouvees),
        "montant_total": round(sum(t["montant"] for t in trouvees), 2),
        "tronque": len(trouvees) > MAX_LIGNES,
        "transactions": trouvees[:MAX_LIGNES],
    }


@tool
def profil_client(client_id: str) -> dict:
    """Donne le profil déclaré d'un client : métier, revenu mensuel déclaré, revenu de l'avis d'imposition,
    patrimoine déclaré, pays de résidence et situation déclarée. Ne contient aucune transaction."""
    return _client(client_id)


@tool
def info_contrepartie(nom: str) -> dict:
    """Donne les informations publiques d'une contrepartie (organisation qui envoie ou reçoit de l'argent) :
    type, pays et informations (financement, commissaire aux comptes, publication des comptes…).
    Le nom doit être celui d'une transaction (champ `contrepartie`)."""
    contreparties = _charger("contreparties.json")
    par_nom = {c["nom"].casefold(): c for c in contreparties}
    trouvee = par_nom.get(nom.strip().casefold())
    if trouvee is None:
        proches = get_close_matches(
            nom.strip().casefold(), list(par_nom), n=3, cutoff=0.5
        )
        suggestion = (
            f" Noms proches : {[par_nom[p]['nom'] for p in proches]}."
            if proches
            else ""
        )
        raise ToolException(f"Contrepartie inconnue : {nom!r}.{suggestion}")
    return trouvee


OUTILS = [historique_client, profil_client, info_contrepartie]

for _outil in OUTILS:
    _outil.handle_tool_error = True
