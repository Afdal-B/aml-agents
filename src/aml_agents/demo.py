"""Déroulé d'une enquête sous forme d'événements sérialisables, pour l'interface et les traces de démo."""

import json
from collections.abc import Iterator
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from aml_agents.schema import Alerte

TRACES = Path(__file__).resolve().parents[2] / "demo" / "traces"


def _texte(contenu) -> str:
    """Le contenu d'un message Gemini peut être une chaîne ou une liste de blocs."""
    if isinstance(contenu, str):
        return contenu
    return "".join(
        b.get("text", "") if isinstance(b, dict) else str(b) for b in contenu or []
    )


def _resultat(contenu) -> dict | str:
    texte = _texte(contenu)
    try:
        return json.loads(texte)
    except ValueError:
        return texte  # message d'erreur d'outil


def derouler(graphe, alerte: Alerte) -> Iterator[dict]:
    """Lance l'enquête et produit un événement par étape :
    pensee (texte du modèle), appel (outil demandé), resultat (réponse de l'outil), rapport."""
    depart = {
        "messages": [
            HumanMessage(f"Alerte à examiner :\n{alerte.model_dump_json(indent=2)}")
        ],
        "alerte": alerte,
    }
    for maj in graphe.stream(
        depart, config={"recursion_limit": 20}, stream_mode="updates"
    ):
        for noeud, sortie in maj.items():
            if noeud == "rediger":
                yield {"type": "rapport", "rapport": sortie["rapport"].model_dump()}
                continue
            for m in sortie.get("messages", []):
                if isinstance(m, AIMessage):
                    if texte := _texte(m.content).strip():
                        yield {"type": "pensee", "texte": texte}
                    for appel in m.tool_calls:
                        yield {"type": "appel", "outil": appel["name"], "args": appel["args"]}
                elif isinstance(m, ToolMessage):
                    yield {"type": "resultat", "outil": m.name, "contenu": _resultat(m.content)}
