"""Enregistre une enquête par alerte dans demo/traces/, rejouée par l'interface sans appel au modèle.

Usage :  uv run python demo/enregistrer.py            # toutes les alertes
         uv run python demo/enregistrer.py ALT-002
Coûte ~8 appels au modèle par alerte.
"""

import json
import sys
from datetime import datetime

from aml_agents.agent_unique.graph import construire_graphe
from aml_agents.compteur import Compteur
from aml_agents.configuration import Configuration, creer_modele
from aml_agents.demo import TRACES, derouler
from aml_agents.outils import DONNEES
from aml_agents.schema import Alerte


def main() -> None:
    config = Configuration.from_env()
    compteur = Compteur(plafond=config.plafond_appels)
    graphe = construire_graphe(creer_modele(config, compteur))
    alertes = [
        Alerte(**a)
        for a in json.loads((DONNEES / "alertes.json").read_text(encoding="utf-8"))
        if len(sys.argv) < 2 or a["id"] in sys.argv[1:]
    ]
    TRACES.mkdir(parents=True, exist_ok=True)
    for alerte in alertes:
        avant = compteur.appels
        evenements = list(derouler(graphe, alerte))
        trace = {
            "alerte_id": alerte.id,
            "modele": config.modele,
            "date": f"{datetime.now():%Y-%m-%d}",
            "appels_modele": compteur.appels - avant,
            "evenements": evenements,
        }
        fichier = TRACES / f"{alerte.id}.json"
        fichier.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"{alerte.id} : {len(evenements)} événements -> {fichier}")


if __name__ == "__main__":
    main()
