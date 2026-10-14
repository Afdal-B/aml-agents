from langchain_core.callbacks import BaseCallbackHandler
from dataclasses import dataclass, field
import threading


class PlafondAtteind(Exception):
    """levée quand le nombre d'appels autorisés est dépassé."""


@dataclass(eq=False)
class Compteur(BaseCallbackHandler):
    raise_error = True
    plafond: int
    appels: int = field(default=0, init=False)
    jetons_entree: int = field(default=0, init=False)
    jeton_sorties: int = field(default=0, init=False)
    _verrou: threading.Lock = field(default_factory=threading.Lock, init=False)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        with self._verrou:
            if self.appels >= self.plafond:
                raise PlafondAtteind(
                    f"Vous avez atteind le plafond de requêtes {self.appels} >= {self.plafond}"
                )
            self.appels += 1

    def on_llm_end(self, response, **kwargs):
        if not response.generations or not response.generations[0]:
            return
        message = getattr(response.generations[0][0], "message", None)
        usage = getattr(message, "usage_metadata", None) or {}
        with self._verrou:
            self.jetons_entree += usage.get("input_tokens", 0)
            self.jeton_sorties += usage.get("output_tokens", 0)
