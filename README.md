# Agent d'enquête anti-blanchiment (LCB-FT)

**[▶️ Démo en ligne](https://aml-agents.streamlit.app/)**

Un agent LLM (LangGraph + Gemini) instruit des alertes de lutte contre le blanchiment ;
**un code déterministe vérifie ses preuves et prend la décision**.

## Principe : l'agent constate, le code décide

1. L'agent enquête avec trois outils en lecture seule (historique, profil client, contrepartie)
   et rend un rapport structuré : des signaux pris dans une liste fermée, chacun appuyé par des
   identifiants de transactions.
2. [`decision.py`](src/aml_agents/decision.py) revérifie chaque constat contre les données. Une preuve
   inventée, appartenant à un autre client ou qui ne démontre pas le signal est écartée.
3. Le score ne porte que sur les constats validés ; des seuils fixes donnent l'issue : classer,
   escalader, ou *proposer* une déclaration de soupçon (validation humaine).

Une hallucination du modèle ne peut donc pas, à elle seule, faire déclarer un client.

## Données

Synthétiques, construites à partir du cas n°13 du rapport Tracfin *LCB-FT : état de la menace
2024-2025* (détournement de subventions via une association). Les montants agrégés sont ceux du
rapport, les noms sont fictifs. Un client légitime déclenche la même règle d'alerte pour mesurer
les faux positifs. Détails : [data/LISEZMOI.md](data/LISEZMOI.md).

## Évaluation (5 exécutions par alerte)

| Alerte | Verdict réel | Issues | Rappel des signaux | Preuves inventées |
|---|---|---|---|---|
| ALT-001 | vrai positif | escalade ×5 | 0,52 | 0 |
| ALT-002 | faux positif | classé sans suite ×5 | — | 0 |

## Lancer en local

```bash
uv sync
cp .env.example .env              # renseigner GOOGLE_API_KEY
uv run streamlit run app.py       # interface
uv run pytest -m "not reseau"     # tests sans appel au modèle
```

Stack : Python 3.12 · LangGraph · Gemini · Pydantic · Streamlit · pytest · uv
