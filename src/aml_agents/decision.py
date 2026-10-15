"""
Le rapport d'un agent est une déclaration. Ici on la vérifie contre les données :
un constat dont les preuves ne tiennent pas est écarté, puis le score et la décision
sont calculés uniquement à partir des constats validés.
"""

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from aml_agents.outils import DONNEES
from aml_agents.schema import (
    Alerte,
    Client,
    Constat,
    Contrepartie,
    Rapport,
    Signal,
    Transaction,
)

# --- Paramètres de la politique (à ajuster ici, nulle part ailleurs) --------------------
POIDS: dict[Signal, int] = {
    "flux_crediteurs_incoherents_avec_activite": 2,
    "flux_incoherents_avec_avis_imposition": 2,
    "retraits_especes_importants": 3,
    "depenses_incoherentes_avec_profil": 2,
    "contrepartie_sans_controle_comptes": 3,
}
SEUIL_DECLARATION = (
    8  # score >= 8 : proposer une déclaration (validation humaine requise)
)
SEUIL_ESCALADE = 3  # score >= 3 : escalader à un analyste ; en dessous, classer

MIN_RETRAITS = 3  # "retraits successifs"
SEUIL_RETRAITS = 10_000  # "montants importants" (total des retraits cités)
RATIO_FLUX_ACTIVITE = 0.5  # crédits cités >= 50 % du revenu annuel déclaré
RATIO_FLUX_AVIS = 1.0  # crédits cités >= 100 % du revenu de l'avis d'imposition
PLANCHER_DEPENSES = (
    5_000  # dépenses de luxe/voyage >= max(patrimoine déclaré, ce plancher)
)
TYPES_LUXE_ET_VOYAGE = {
    "bijouterie",
    "horlogerie",
    "pret_a_porter_luxe",
    "agence_voyages",
    "compagnie_aerienne",
    "hotel",
}

Issue = Literal["classer_sans_suite", "escalade_humaine", "declaration_proposee"]


# --- Résultats ----------------------------------------------------------------------------
class ConstatVerifie(BaseModel):
    model_config = ConfigDict(frozen=True)
    constat: Constat
    valide: bool
    raison: str  # pourquoi il est écarté, ou "ok"


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)
    alerte_id: str
    issue: Issue
    score: int
    constats_verifies: list[ConstatVerifie]

    @property
    def constats_invalides(self) -> list[ConstatVerifie]:
        return [v for v in self.constats_verifies if not v.valide]


# --- Données ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Donnees:
    clients: dict[str, Client]
    transactions: dict[str, Transaction]
    contreparties: dict[str, Contrepartie]


def charger_donnees() -> Donnees:
    def lire(nom):
        return json.loads((DONNEES / nom).read_text(encoding="utf-8"))

    return Donnees(
        clients={c["id"]: Client(**c) for c in lire("clients.json")},
        transactions={t["id"]: Transaction(**t) for t in lire("transactions.json")},
        contreparties={c["nom"]: Contrepartie(**c) for c in lire("contreparties.json")},
    )


# --- Vérification d'un constat ----------------------------------------------------------
# Chaque fonction renvoie le motif de rejet (texte), ou None si tout est en ordre.


def _motif_preuves(preuves: list[str], alerte: Alerte, donnees: Donnees) -> str | None:
    """Contrôles valables pour tous les signaux : les preuves existent et concernent ce client."""
    inconnues = [p for p in preuves if p not in donnees.transactions]
    if inconnues:
        return f"preuves inexistantes : {inconnues}"
    txs = [donnees.transactions[p] for p in preuves]
    etrangeres = [t.id for t in txs if t.client_id != alerte.client_id]
    if etrangeres:
        return f"preuves d'un autre client : {etrangeres}"
    futures = [t.id for t in txs if t.date > alerte.date_alerte]
    if futures:
        return f"preuves postérieures à l'alerte : {futures}"
    return None


def _motif_signal(
    signal: Signal, txs: list[Transaction], alerte: Alerte, donnees: Donnees
) -> str | None:
    """Contrôles propres à chaque signal : les preuves démontrent-elles vraiment ce qu'il affirme ?"""
    client = donnees.clients[alerte.client_id]
    total = round(sum(t.montant for t in txs), 2)

    if signal == "retraits_especes_importants":
        if any(t.mode != "especes" or t.sens != "debit" for t in txs):
            return "toutes les preuves doivent être des retraits d'espèces"
        if len(txs) < MIN_RETRAITS:
            return f"{len(txs)} retrait(s) cité(s), il en faut au moins {MIN_RETRAITS}"
        if total < SEUIL_RETRAITS:
            return f"total des retraits {total} € inférieur à {SEUIL_RETRAITS} €"

    elif signal in (
        "flux_crediteurs_incoherents_avec_activite",
        "flux_incoherents_avec_avis_imposition",
    ):
        if any(t.sens != "credit" for t in txs):
            return "toutes les preuves doivent être des crédits"
        if signal == "flux_crediteurs_incoherents_avec_activite":
            seuil = RATIO_FLUX_ACTIVITE * 12 * client.revenu_mensuel_declare
        else:
            seuil = RATIO_FLUX_AVIS * client.revenu_annuel_avis_imposition
        if total < seuil:
            return f"total des crédits {total} € inférieur au seuil {seuil:.0f} €"

    elif signal == "depenses_incoherentes_avec_profil":
        if any(t.sens != "debit" for t in txs):
            return "toutes les preuves doivent être des dépenses"
        for t in txs:
            fiche = donnees.contreparties.get(t.contrepartie)
            if fiche is None or fiche.type not in TYPES_LUXE_ET_VOYAGE:
                return f"{t.id} n'est ni une dépense de luxe ni un voyage"
        seuil = max(client.patrimoine_declare, PLANCHER_DEPENSES)
        if total < seuil:
            return f"total des dépenses {total} € inférieur au seuil {seuil:.0f} €"

    elif signal == "contrepartie_sans_controle_comptes":
        if any(t.contrepartie != alerte.contrepartie for t in txs):
            return "les preuves doivent concerner la contrepartie de l'alerte"
        info = donnees.contreparties[alerte.contrepartie].informations
        if (
            "commissaire_aux_comptes_designe" not in info
            or "comptes_publies_joafe" not in info
        ):
            return (
                "informations de contrôle des comptes absentes : impossible à vérifier"
            )
        if info["commissaire_aux_comptes_designe"] or info["comptes_publies_joafe"]:
            return "la contrepartie a un commissaire aux comptes ou publie ses comptes"

    return None


def verifier_constat(
    constat: Constat, alerte: Alerte, donnees: Donnees
) -> ConstatVerifie:
    preuves = list(dict.fromkeys(constat.preuves))
    motif = _motif_preuves(preuves, alerte, donnees)
    if motif is None:
        txs = [donnees.transactions[p] for p in preuves]
        motif = _motif_signal(constat.signal, txs, alerte, donnees)
    return ConstatVerifie(constat=constat, valide=motif is None, raison=motif or "ok")


# --- Score et décision ------------------------------------------------------------------
def decider(alerte: Alerte, rapport: Rapport, donnees: Donnees) -> Decision:
    verifies = [verifier_constat(c, alerte, donnees) for c in rapport.constats]
    signaux_retenus = {
        v.constat.signal for v in verifies if v.valide
    }  # un signal compte une fois
    score = sum(POIDS[s] for s in signaux_retenus)
    if score >= SEUIL_DECLARATION:
        issue: Issue = "declaration_proposee"
    elif score >= SEUIL_ESCALADE:
        issue = "escalade_humaine"
    else:
        issue = "classer_sans_suite"
    return Decision(
        alerte_id=alerte.id, issue=issue, score=score, constats_verifies=verifies
    )
