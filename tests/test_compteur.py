import pytest

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from aml_agents.compteur import Compteur, PlafondAtteind
from aml_agents.configuration import Configuration, creer_modele


def test_plafond():
    compteur = Compteur(plafond=0)
    modele = GenericFakeChatModel(messages=iter(["ok"]), callbacks=[compteur])
    with pytest.raises(PlafondAtteind):
        modele.invoke("test")


def test_comptage():
    compteur = Compteur(plafond=5)
    modele = GenericFakeChatModel(
        messages=iter(["ok", "ok", "ok"]), callbacks=[compteur]
    )
    modele.invoke("a")
    modele.invoke("b")
    modele.invoke("c")
    assert compteur.appels == 3


@pytest.mark.reseau
def test_appel_llm():
    config = Configuration.from_env()
    compteur = Compteur(config.plafond_appels)
    modele = creer_modele(config, compteur)
    modele.invoke("Repond uniquement par le mot: test")
    print(compteur)
    assert compteur.appels == 1
    assert compteur.jetons_entree > 0
