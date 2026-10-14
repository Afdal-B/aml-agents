import json
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from aml_agents.agent_unique.graph import construire_graphe, enqueter
from aml_agents.agent_unique.prompt import prompt_systeme
from aml_agents.schema import Alerte, Constat, Rapport

DONNEES = Path(__file__).resolve().parents[1] / "data"


def charger(nom):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


class FauxModele(GenericFakeChatModel):
    """Modèle scripté : GenericFakeChatModel ne sait faire ni bind_tools ni with_structured_output."""

    rapport: Rapport | None = None

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _: self.rapport)


def alerte_001():
    return Alerte(**charger("alertes.json")[0])


def test_graphe_compile_avec_les_trois_noeuds():
    noeuds = set(construire_graphe(FauxModele(messages=iter([]))).get_graph().nodes)
    assert {"agent", "tools", "rediger"} <= noeuds


def test_prompt_contient_les_cinq_signaux():
    prompt = prompt_systeme()
    ids = [s["id"] for s in charger("signaux.json")]
    assert len(ids) == 5 and all(i in prompt for i in ids)


def test_boucle_avec_un_outil_puis_rapport():
    appel = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "historique_client",
                "id": "t1",
                "args": {"client_id": "CLI-003", "jours": 730, "mode": "especes"},
            }
        ],
    )
    fin = AIMessage(content="J'ai terminé.")
    attendu = Rapport(
        constats=[
            Constat(
                signal="retraits_especes_importants",
                preuves=["TX-000001"],
                explication="x",
            )
        ],
        synthese="Retraits d'espèces importants.",
    )
    graphe = construire_graphe(FauxModele(messages=iter([appel, fin]), rapport=attendu))
    etat = graphe.invoke({"messages": [HumanMessage("alerte")], "alerte": alerte_001()})

    outils = [m for m in etat["messages"] if isinstance(m, ToolMessage)]
    assert len(outils) == 1 and "nombre_transactions" in outils[0].content
    assert etat["rapport"] == attendu


def test_enqueter_renvoie_le_rapport():
    rapport = Rapport(constats=[], synthese="Rien à signaler.")
    graphe = construire_graphe(
        FauxModele(messages=iter([AIMessage(content="ok")]), rapport=rapport)
    )
    assert enqueter(graphe, alerte_001()) == rapport


@pytest.mark.reseau
@pytest.mark.parametrize("indice", [0, 1])
def test_enquete_reelle(indice):
    from aml_agents.compteur import Compteur
    from aml_agents.configuration import Configuration, creer_modele

    config = Configuration.from_env()
    compteur = Compteur(plafond=config.plafond_appels)
    graphe = construire_graphe(creer_modele(config, compteur))
    rapport = enqueter(graphe, Alerte(**charger("alertes.json")[indice]))
    print(compteur)
    print(rapport.model_dump_json(indent=2))

    ids = {t["id"] for t in charger("transactions.json")}
    for c in rapport.constats:
        assert set(c.preuves) <= ids, f"preuves inventées : {set(c.preuves) - ids}"
    assert compteur.appels <= config.plafond_appels
