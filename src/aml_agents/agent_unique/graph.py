from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from aml_agents.agent_unique.prompt import prompt_systeme
from aml_agents.agent_unique.state import Etat
from aml_agents.outils import OUTILS
from aml_agents.schema import Alerte, Rapport

CONSIGNE_FINALE = (
    "Rédige maintenant le rapport final de ton enquête : les signaux retenus avec leurs preuves "
    "(identifiants de transactions que tu as vus), et une synthèse. Si rien n'est retenu, liste vide."
)


def construire_graphe(modele):
    avec_outils = modele.bind_tools(OUTILS)
    redacteur = modele.with_structured_output(Rapport)

    def agent(etat: Etat) -> dict:
        reponse = avec_outils.invoke(
            [SystemMessage(prompt_systeme())] + etat["messages"]
        )
        return {"messages": [reponse]}

    def rediger(etat: Etat) -> dict:
        messages = (
            [SystemMessage(prompt_systeme())]
            + etat["messages"]
            + [HumanMessage(CONSIGNE_FINALE)]
        )
        return {"rapport": redacteur.invoke(messages)}

    graphe = StateGraph(Etat)
    graphe.add_node("agent", agent)
    graphe.add_node("tools", ToolNode(OUTILS))
    graphe.add_node("rediger", rediger)
    graphe.add_edge(START, "agent")
    graphe.add_conditional_edges(
        "agent", tools_condition, {"tools": "tools", END: "rediger"}
    )
    graphe.add_edge("tools", "agent")
    graphe.add_edge("rediger", END)
    return graphe.compile()


def enqueter(graphe, alerte: Alerte) -> Rapport:
    """Lance l'enquête sur une alerte et renvoie le rapport."""
    depart = {
        "messages": [
            HumanMessage(f"Alerte à examiner :\n{alerte.model_dump_json(indent=2)}")
        ],
        "alerte": alerte,
    }
    return graphe.invoke(depart, config={"recursion_limit": 20})["rapport"]
