import json
from pathlib import Path

import pytest

from aml_agents.decision import charger_donnees, decider
from aml_agents.metriques import agreger, charger_verite, mesurer
from aml_agents.schema import Alerte, Constat, Rapport

DONNEES = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def donnees():
    return charger_donnees()


@pytest.fixture(scope="module")
def verite():
    return charger_verite()


@pytest.fixture(scope="module")
def alertes():
    brut = json.loads((DONNEES / "alertes.json").read_text(encoding="utf-8"))
    return {a["id"]: Alerte(**a) for a in brut}


def rapport(*constats):
    return Rapport(constats=list(constats), synthese="test")


def constat(signal, preuves):
    return Constat(signal=signal, preuves=list(preuves), explication="test")


def mesure_de(id_alerte, rap, alertes, donnees, verite):
    decision = decider(alertes[id_alerte], rap, donnees)
    return mesurer(decision, rap, verite[id_alerte], donnees)


def rapport_parfait(verite):
    preuves = verite["ALT-001"]["preuves"]
    return rapport(*(constat(s, p) for s, p in preuves.items()))


def test_rapport_parfait_rappel_total(alertes, donnees, verite):
    m = mesure_de("ALT-001", rapport_parfait(verite), alertes, donnees, verite)
    assert m.rappel_signaux == 1.0
    assert not m.faux_negatif and m.constats_invalides == 0
    assert m.issue == "declaration_proposee"


def test_rapport_vide_sur_vrai_positif_est_un_faux_negatif(alertes, donnees, verite):
    m = mesure_de("ALT-001", rapport(), alertes, donnees, verite)
    assert (
        m.faux_negatif and m.rappel_signaux == 0.0 and m.issue == "classer_sans_suite"
    )


def test_accusation_sur_le_sosie_est_invalidee_sans_faux_positif(
    alertes, donnees, verite
):
    preuves = verite["ALT-001"]["preuves"]["retraits_especes_importants"]
    m = mesure_de(
        "ALT-002",
        rapport(constat("retraits_especes_importants", preuves)),
        alertes,
        donnees,
        verite,
    )
    assert m.constats_emis == 1 and m.constats_invalides == 1
    assert not m.faux_positif and m.issue == "classer_sans_suite"
    assert m.rappel_signaux is None  # aucun signal attendu


def test_preuve_inventee_est_comptee(alertes, donnees, verite):
    rap = rapport(constat("retraits_especes_importants", ["TX-999999", "TX-999998"]))
    m = mesure_de("ALT-001", rap, alertes, donnees, verite)
    assert m.preuves_inexistantes == 2 and m.constats_invalides == 1


def test_agregation_de_plusieurs_executions(alertes, donnees, verite):
    mesures = [
        mesure_de("ALT-001", rapport_parfait(verite), alertes, donnees, verite),
        mesure_de("ALT-001", rapport(), alertes, donnees, verite),
        mesure_de(
            "ALT-001",
            rapport(constat("retraits_especes_importants", ["TX-999999"])),
            alertes,
            donnees,
            verite,
        ),
    ]
    r = agreger(mesures, echecs=1)
    assert r["executions_reussies"] == 3 and r["executions_echouees"] == 1
    assert r["issues"] == {"declaration_proposee": 1, "classer_sans_suite": 2}
    assert r["faux_negatifs"] == 2
    assert r["rappel_moyen"] == pytest.approx(1 / 3, abs=1e-3)
    assert r["preuves_inexistantes"] == 1 and r["constats_invalides"] == 1
