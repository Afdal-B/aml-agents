"""Modèles de données : entrées (données du dossier) et sortie des agents (Constat)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Signal = Literal[
    "flux_crediteurs_incoherents_avec_activite",
    "flux_incoherents_avec_avis_imposition",
    "retraits_especes_importants",
    "depenses_incoherentes_avec_profil",
    "contrepartie_sans_controle_comptes",
]


class _Modele(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Client(_Modele):
    id: str
    nom: str
    type_compte: str
    metier: str
    revenu_mensuel_declare: float
    revenu_annuel_avis_imposition: float
    patrimoine_declare: float
    pays_residence: str
    solde_initial: float
    situation_declaree: str


class Transaction(_Modele):
    id: str
    client_id: str
    date: date
    montant: float = Field(gt=0)
    sens: Literal["credit", "debit"]
    mode: Literal["virement", "prelevement", "carte", "especes"]
    libelle: str
    contrepartie: str
    pays_contrepartie: str


class Contrepartie(_Modele):
    nom: str
    type: str
    pays: str
    informations: dict


class Alerte(_Modele):
    id: str
    client_id: str
    regle: str
    libelle_regle: str
    date_alerte: date
    contrepartie: str
    montant_cumule: float
    nombre_credits: int


class Constat(_Modele):
    signal: Signal
    preuves: list[str] = Field(
        min_length=1, description="Identifiants de transactions, ex. TX-000123"
    )
    explication: str = Field(
        min_length=1, description="Justification courte, en français"
    )


class Rapport(_Modele):
    constats: list[Constat] = Field(
        description="Signaux retenus ; liste vide si rien n'est retenu"
    )
    synthese: str = Field(
        min_length=1, description="Résumé de l'enquête en 2 à 4 phrases, en français"
    )
