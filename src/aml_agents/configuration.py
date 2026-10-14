from dataclasses import dataclass
from dotenv import load_dotenv
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from aml_agents.compteur import Compteur
from langchain_core.rate_limiters import InMemoryRateLimiter


@dataclass(frozen=True)
class Configuration:
    modele: str = "gemini-3.1-flash-lite"
    plafond_appels: int = 50
    requetes_par_seconde: float = 0.2

    @classmethod
    def from_env(cls) -> "Configuration":
        load_dotenv()
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY absente dans .env")
        return cls(
            modele=os.getenv("MODELE") or cls.modele,
            requetes_par_seconde=os.getenv("REQUETES_PAR_SECONDES")
            or cls.requetes_par_seconde,
        )


def creer_modele(config: Configuration, compteur: Compteur) -> ChatGoogleGenerativeAI:
    limiteur = InMemoryRateLimiter(requests_per_second=config.requetes_par_seconde)
    return ChatGoogleGenerativeAI(
        model=config.modele, rate_limiter=limiteur, callbacks=[compteur], max_retries=2
    )
