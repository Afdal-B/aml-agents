from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from aml_agents.schema import Alerte, Rapport


class Etat(TypedDict):
    messages: Annotated[list, add_messages]
    alerte: Alerte
    rapport: Rapport | None
