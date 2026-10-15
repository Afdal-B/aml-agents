import json
from pathlib import Path

import pytest

from aml_agents.decision import POIDS, charger_donnees, decider, verifier_constat
from aml_agents.schema import Alerte, Constat, Rapport

DONNEES = Path(__file__).resolve().parents[1] / "data"


def charger(nom):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def donnees():
    return charger_donnees()


@pytest.fixture(scope="module")
def alertes():
    return {a["id"]: Alerte(**a) for a in charger("alertes.json")}


def constat(signal, preuves):
    return Constat(signal=signal, preuves=list(preuves), explication="test")


def rapport(*constats):
    return Rapport(constats=list(constats), synthese="test")


def preuves_attendues(id_alerte):
    """Les transactions-preuves de la vérité terrain : réservées aux tests, jamais aux agents."""
    return charger("verite.json")["alertes"][id_alerte]["preuves"]


def credits_de_l_alerte(donnees, alerte):
    debut = alerte.date_alerte.toordinal() - 89
    return [
        t.id
        for t in donnees.transactions.values()
        if t.client_id == alerte.client_id
        and t.sens == "credit"
        and t.contrepartie == alerte.contrepartie
        and t.date.toordinal() >= debut
    ]


def test_rapport_complet_sur_le_vrai_cas(donnees, alertes):
    rapp = rapport(*[constat(s, p) for s, p in preuves_attendues("ALT-001").items()])
    d = decider(alertes["ALT-001"], rapp, donnees)
    assert d.constats_invalides == []
    assert d.score == sum(POIDS.values())
    assert d.issue == "declaration_proposee"


def test_rapport_vide_est_classe(donnees, alertes):
    d = decider(alertes["ALT-002"], rapport(), donnees)
    assert (d.score, d.issue) == (0, "classer_sans_suite")


def test_rapport_partiel_reel_escalade(donnees, alertes):
    """La sortie réelle de l'agent unique : 2 signaux sur 5, preuves = les 3 virements de la fenêtre."""
    ids = ["TX-002103", "TX-002201", "TX-002299"]
    rapp = rapport(
        constat("flux_incoherents_avec_avis_imposition", ids),
        constat("contrepartie_sans_controle_comptes", ids),
    )
    d = decider(alertes["ALT-001"], rapp, donnees)
    assert d.constats_invalides == []
    assert (d.score, d.issue) == (5, "escalade_humaine")


def test_preuve_inventee_est_ecartee(donnees, alertes):
    v = verifier_constat(
        constat("retraits_especes_importants", ["TX-999999"]),
        alertes["ALT-001"],
        donnees,
    )
    assert not v.valide and "inexistantes" in v.raison


def test_preuve_d_un_autre_client_est_ecartee(donnees, alertes):
    retraits_du_couple = preuves_attendues("ALT-001")["retraits_especes_importants"]
    v = verifier_constat(
        constat("retraits_especes_importants", retraits_du_couple),
        alertes["ALT-002"],
        donnees,
    )
    assert not v.valide and "autre client" in v.raison


def test_preuve_qui_ne_correspond_pas_au_signal(donnees, alertes):
    credits = credits_de_l_alerte(donnees, alertes["ALT-001"])
    v = verifier_constat(
        constat("retraits_especes_importants", credits), alertes["ALT-001"], donnees
    )
    assert not v.valide and "retraits d'espèces" in v.raison


def test_le_sosie_ne_peut_pas_etre_accuse(donnees, alertes):
    """Même si un agent se trompe, le code écarte ses accusations contre le client légitime."""
    credits = credits_de_l_alerte(donnees, alertes["ALT-002"])
    assert credits
    rapp = rapport(
        constat("flux_incoherents_avec_avis_imposition", credits),
        constat("flux_crediteurs_incoherents_avec_activite", credits),
        constat("contrepartie_sans_controle_comptes", credits),
    )
    d = decider(alertes["ALT-002"], rapp, donnees)
    assert len(d.constats_invalides) == 3
    assert (d.score, d.issue) == (0, "classer_sans_suite")


def test_un_signal_repete_compte_une_fois(donnees, alertes):
    ids = ["TX-002103", "TX-002201", "TX-002299"]
    c = constat("contrepartie_sans_controle_comptes", ids)
    d = decider(alertes["ALT-001"], rapport(c, c, c), donnees)
    assert d.score == POIDS["contrepartie_sans_controle_comptes"]


def test_preuves_en_double_ne_gonflent_pas_le_total(donnees, alertes):
    un_seul_retrait = (
        preuves_attendues("ALT-001")["retraits_especes_importants"][:1] * 5
    )
    v = verifier_constat(
        constat("retraits_especes_importants", un_seul_retrait),
        alertes["ALT-001"],
        donnees,
    )
    assert not v.valide and "au moins" in v.raison


def test_decision_inchangeable(donnees, alertes):
    d = decider(alertes["ALT-002"], rapport(), donnees)
    with pytest.raises(Exception):
        d.score = 99
