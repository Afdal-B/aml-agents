"""Interface de démonstration : un agent LangGraph trie des alertes de lutte contre le blanchiment.

Lancement local :  uv run streamlit run app.py
"""

import json
import sys
import threading
import time
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from aml_agents.agent_unique.graph import construire_graphe  # noqa: E402
from aml_agents.compteur import Compteur, PlafondAtteind  # noqa: E402
from aml_agents.configuration import Configuration, creer_modele  # noqa: E402
from aml_agents.decision import (  # noqa: E402
    POIDS,
    SEUIL_DECLARATION,
    SEUIL_ESCALADE,
    charger_donnees,
    decider,
)
from aml_agents.demo import TRACES, derouler  # noqa: E402
from aml_agents.outils import DONNEES  # noqa: E402
from aml_agents.schema import Alerte, Rapport  # noqa: E402

PLAFOND_PAR_ENQUETE = 15  # appels au modèle autorisés pour une enquête
QUOTA_JOUR = 150  # appels au modèle par jour, tous visiteurs confondus (quota gratuit : 500)
BASELINE = RACINE / "docs" / "baseline_agent_unique.json"

st.set_page_config(page_title="Agent LCB-FT", page_icon="🔎", layout="wide")


# --- Données ------------------------------------------------------------------------------
@st.cache_data
def lire(nom: str):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


@st.cache_resource
def donnees():
    return charger_donnees()


@st.cache_data
def transactions() -> pd.DataFrame:
    df = pd.DataFrame(lire("transactions.json"))
    df["date"] = pd.to_datetime(df["date"])
    return df


ALERTES = {a["id"]: Alerte(**a) for a in lire("alertes.json")}
CLIENTS = {c["id"]: c for c in lire("clients.json")}
SIGNAUX = {s["id"]: s["critere_tracfin"] for s in lire("signaux.json")}
VERITE = lire("verite.json")["alertes"]

ISSUES = {
    "classer_sans_suite": ("Classer sans suite", "🟢"),
    "escalade_humaine": ("Escalader à un analyste", "🟠"),
    "declaration_proposee": ("Proposer une déclaration de soupçon", "🔴"),
}


def euros(x: float) -> str:
    return f"{x:,.0f} €".replace(",", " ")


# --- Quota partagé entre visiteurs ----------------------------------------------------------
@st.cache_resource
def quota() -> dict:
    return {"jour": date.today(), "appels": 0, "verrou": threading.Lock()}


def appels_restants() -> int:
    q = quota()
    with q["verrou"]:
        if q["jour"] != date.today():
            q["jour"], q["appels"] = date.today(), 0
        return QUOTA_JOUR - q["appels"]


def consommer(n: int) -> None:
    q = quota()
    with q["verrou"]:
        q["appels"] += n


def configuration() -> Configuration | None:
    try:
        return Configuration.from_env()
    except RuntimeError:
        return None


# --- Affichage d'une enquête ----------------------------------------------------------------
def afficher_resultat(outil: str, contenu) -> None:
    if isinstance(contenu, str):
        st.warning(contenu)
    elif outil == "historique_client":
        c1, c2, c3 = st.columns(3)
        c1.metric("Transactions", contenu["nombre_transactions"])
        c2.metric("Montant total", euros(contenu["montant_total"]))
        c3.metric("Période", f"{contenu['du']} → {contenu['au']}")
        if contenu["tronque"]:
            st.caption("Réponse tronquée aux 100 transactions les plus récentes.")
        colonnes = ["id", "date", "montant", "sens", "mode", "libelle", "contrepartie"]
        st.dataframe(
            pd.DataFrame(contenu["transactions"])[colonnes] if contenu["transactions"] else None,
            hide_index=True,
            width="stretch",
            height=240,
        )
    else:
        st.json(contenu)


def afficher_evenement(e: dict) -> None:
    if e["type"] == "pensee":
        with st.chat_message("assistant", avatar="🧠"):
            st.markdown(e["texte"])
    elif e["type"] == "appel":
        args = ", ".join(f"{k}={v!r}" for k, v in e["args"].items())
        with st.chat_message("assistant", avatar="🛠️"):
            st.markdown(f"L'agent appelle `{e['outil']}({args})`")
    elif e["type"] == "resultat":
        with st.chat_message("user", avatar="📄"):
            with st.expander(f"Réponse de `{e['outil']}`"):
                afficher_resultat(e["outil"], e["contenu"])


def afficher_rapport(rapport: Rapport) -> None:
    st.markdown("#### 📝 Rapport de l'agent")
    st.info(rapport.synthese)
    if not rapport.constats:
        st.markdown("_Aucun signal retenu._")
    for c in rapport.constats:
        st.markdown(f"- **{c.signal}** : {c.explication}  \n  preuves : `{', '.join(c.preuves)}`")


def afficher_decision(alerte: Alerte, rapport: Rapport) -> None:
    decision = decider(alerte, rapport, donnees())
    libelle, pastille = ISSUES[decision.issue]

    st.markdown("#### ⚖️ Décision calculée par le code")
    st.caption(
        "Chaque constat est revérifié contre les données (les preuves existent, concernent ce client, "
        "démontrent le signal). Seuls les constats validés comptent dans le score."
    )
    if decision.constats_verifies:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Signal": v.constat.signal,
                        "Validé": "✅" if v.valide else "❌",
                        "Poids": POIDS[v.constat.signal] if v.valide else 0,
                        "Motif": v.raison,
                    }
                    for v in decision.constats_verifies
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    c1, c2 = st.columns([1, 2])
    c1.metric("Score", f"{decision.score} / {sum(POIDS.values())}")
    c2.markdown(f"### {pastille} {libelle}")
    c2.caption(
        f"Seuils : escalade à partir de {SEUIL_ESCALADE}, déclaration proposée à partir de "
        f"{SEUIL_DECLARATION} (toujours soumise à validation humaine)."
    )

    with st.expander("🎯 Révéler la vérité terrain"):
        verite = VERITE[alerte.id]
        attendus = set(verite["signaux_attendus"])
        trouves = {v.constat.signal for v in decision.constats_verifies if v.valide}
        if verite["verdict"] == "vrai_positif":
            st.error("**Vrai positif** : c'est le cas n°13 du rapport Tracfin 2024-2025.")
            st.markdown(f"Signaux retrouvés : **{len(trouves & attendus)} / {len(attendus)}**")
            for s in sorted(attendus):
                st.markdown(f"- {'✅' if s in trouves else '⬜'} {s}")
        else:
            st.success(
                "**Faux positif** : client légitime, déclenché par la même règle que le vrai cas. "
                "La bonne issue est de classer sans suite."
            )
        bon = (verite["verdict"] == "vrai_positif") != (decision.issue == "classer_sans_suite")
        st.markdown("Issue correcte ✅" if bon else "Issue incorrecte ❌")


def rendre(evenements: list[dict], alerte: Alerte, pause: float = 0.0) -> None:
    rapport = None
    for e in evenements:
        if e["type"] == "rapport":
            rapport = Rapport(**e["rapport"])
        else:
            afficher_evenement(e)
            time.sleep(pause)
    if rapport:
        st.divider()
        afficher_rapport(rapport)
        afficher_decision(alerte, rapport)


def enquete_en_direct(alerte: Alerte, config: Configuration) -> list[dict] | None:
    compteur = Compteur(plafond=PLAFOND_PAR_ENQUETE)
    graphe = construire_graphe(creer_modele(config, compteur))
    evenements = []
    try:
        with st.spinner("L'agent enquête… (Gemini, ~20 s)"):
            for e in derouler(graphe, alerte):
                evenements.append(e)
                if e["type"] != "rapport":
                    afficher_evenement(e)
    except PlafondAtteind:
        st.error("L'agent a dépassé le nombre d'appels autorisés pour une enquête.")
        return None
    except Exception as e:  # quota Gemini, réseau…
        st.error(f"L'enquête a échoué : {type(e).__name__}. Essayez le mode « rejouer ».")
        return None
    finally:
        consommer(compteur.appels)
    return evenements


# --- Onglets --------------------------------------------------------------------------------
def onglet_enquete() -> None:
    gauche, droite = st.columns([1, 2], gap="large")
    with gauche:
        id_alerte = st.radio(
            "Alerte",
            list(ALERTES),
            format_func=lambda i: f"{i} · {CLIENTS[ALERTES[i].client_id]['nom']}",
        )
        alerte = ALERTES[id_alerte]
        client = CLIENTS[alerte.client_id]
        with st.container(border=True):
            st.markdown(f"**Règle {alerte.regle}** : {alerte.libelle_regle}")
            st.markdown(
                f"**Client** : {client['nom']} ({alerte.client_id})  \n"
                f"**Contrepartie** : {alerte.contrepartie}  \n"
                f"**Cumul 90 j** : {euros(alerte.montant_cumule)} en {alerte.nombre_credits} crédits"
            )
        st.caption("Les deux alertes sont levées par la même règle : seule l'enquête les distingue.")

        config = configuration()
        restants = appels_restants()
        direct_possible = config is not None and restants >= PLAFOND_PAR_ENQUETE
        modes = ["Rejouer une enquête enregistrée", "Lancer l'agent en direct"]
        mode = st.radio("Mode", modes, help="Le mode direct appelle Gemini ; le mode rejouer est instantané.")
        if mode == modes[1] and not direct_possible:
            st.warning(
                "Mode direct indisponible (clé API absente ou quota du jour épuisé). "
                "Utilisez le mode rejouer."
            )
        lancer = st.button(
            "▶️ Lancer l'enquête",
            type="primary",
            width="stretch",
            disabled=mode == modes[1] and not direct_possible,
        )
        if config is not None:
            st.caption(f"Appels au modèle restants aujourd'hui : {max(restants, 0)} / {QUOTA_JOUR}")

    with droite:
        traces = st.session_state.setdefault("traces", {})
        if lancer and mode == modes[0]:
            trace = json.loads((TRACES / f"{id_alerte}.json").read_text(encoding="utf-8"))
            traces[id_alerte] = {"evenements": trace["evenements"], "source": f"enregistrée le {trace['date']} ({trace['modele']})"}
            st.caption(f"Enquête {traces[id_alerte]['source']}")
            rendre(trace["evenements"], alerte, pause=0.6)
        elif lancer:
            evenements = enquete_en_direct(alerte, config)
            if evenements:
                traces[id_alerte] = {"evenements": evenements, "source": f"en direct ({config.modele})"}
                st.rerun()
        elif id_alerte in traces:
            st.caption(f"Enquête {traces[id_alerte]['source']}")
            rendre(traces[id_alerte]["evenements"], alerte)
        else:
            st.markdown(
                "#### Choisissez une alerte et lancez l'enquête\n"
                "Vous verrez l'agent interroger ses trois outils, rédiger un rapport structuré, "
                "puis le code vérifier chaque preuve et calculer la décision."
            )


def onglet_projet() -> None:
    st.markdown(
        """
### Le problème
Dans une banque, les règles de détection lèvent beaucoup d'alertes, dont une majorité de faux positifs.
Chaque alerte demande à un analyste LCB-FT de croiser l'historique du client, son profil déclaré
et les contreparties. Ce projet confie cette enquête à un agent LLM, **sans lui laisser la décision**.

### Le principe : l'agent constate, le code décide
1. **L'agent** (LangGraph + Gemini) enquête avec trois outils en lecture seule et rend un rapport
   structuré (Pydantic) : des signaux pris dans une liste fermée, chacun appuyé par des identifiants
   de transactions.
2. **Le code** (`decision.py`) revérifie chaque constat contre les données : une preuve inventée,
   appartenant à un autre client ou qui ne démontre pas le signal est écartée.
3. **Le score** ne porte que sur les constats validés ; des seuils fixes donnent l'issue. Une
   déclaration de soupçon n'est jamais qu'une *proposition* soumise à un humain.

Une hallucination du modèle ne peut donc pas, à elle seule, faire déclarer un client.
"""
    )
    st.graphviz_chart(
        """
digraph {
  rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2ff", fontname="Helvetica"];
  alerte [label="Alerte (règle R1)"];
  agent [label="Agent LLM\\n(Gemini)", fillcolor="#fde68a"];
  outils [label="Outils\\nhistorique · profil · contrepartie"];
  rediger [label="Rapport structuré\\n(Pydantic)", fillcolor="#fde68a"];
  verif [label="Vérification\\ndes preuves", fillcolor="#bbf7d0"];
  score [label="Score + seuils", fillcolor="#bbf7d0"];
  issue [label="Classer · Escalader\\n· Proposer une déclaration"];
  alerte -> agent; agent -> outils [dir=both]; agent -> rediger -> verif -> score -> issue;
}
"""
    )
    st.markdown(
        f"""
### Les données
Synthétiques, construites à partir du **cas n°13 du rapport Tracfin 2024-2025** (« Détournement de fonds
publics via une association ») : un couple détourne 600 k€ de subventions d'une association qu'il dirige.
Les montants agrégés sont ceux du rapport ; les noms sont fictifs. Pour mesurer les faux positifs,
un **sosie légitime** (CLI-005) déclenche la même règle d'alerte.

Les cinq signaux sont les critères d'alerte du rapport, mot pour mot :
"""
        + "\n".join(f"- `{k}` (poids {POIDS[k]}) : {v}" for k, v in SIGNAUX.items())
        + """

Source : [Tracfin, LCB-FT : état de la menace 2024-2025](https://www.economie.gouv.fr/files/files/directions_services/tracfin/media-document/TRACFIN_2024_Tome3_FR_WEB_0.pdf),
Licence Ouverte Etalab 2.0.

### Stack
Python 3.12 · LangGraph · LangChain · Gemini · Pydantic · pytest · Streamlit · uv
"""
    )


def onglet_evaluation() -> None:
    if not BASELINE.exists():
        st.info("Aucune évaluation publiée.")
        return
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    st.markdown(
        f"Chaque alerte est instruite **{base['runs']} fois** (le modèle n'est pas déterministe), "
        "puis chaque décision est comparée à la vérité terrain."
    )
    resumes = {a: r["resume"] for a, r in base["alertes"].items()}
    c = st.columns(4)
    c[0].metric("Faux négatifs", sum(r["faux_negatifs"] for r in resumes.values()))
    c[1].metric("Faux positifs", sum(r["faux_positifs"] for r in resumes.values()))
    c[2].metric("Preuves inventées", sum(r["preuves_inexistantes"] for r in resumes.values()))
    c[3].metric("Appels au modèle", base["appels"])

    lignes = []
    for a, r in base["alertes"].items():
        s = r["resume"]
        lignes.append(
            {
                "Alerte": a,
                "Verdict réel": r["verdict"],
                "Issues": ", ".join(f"{ISSUES[k][0]} ×{v}" for k, v in s["issues"].items()),
                "Score moyen": s["score_moyen"],
                "Rappel des signaux": s["rappel_moyen"],
                "Constats invalides": f"{s['constats_invalides']} / {s['constats_emis']}",
                "Durée moyenne (s)": s["duree_moyenne_s"],
            }
        )
    st.dataframe(pd.DataFrame(lignes), hide_index=True, width="stretch")
    st.markdown(
        "**Lecture** : aucune erreur de tri, aucune preuve inventée. Le vrai positif est toujours "
        "escaladé, mais l'agent ne retrouve en moyenne qu'une partie des signaux attendus : c'est la "
        "piste d'amélioration (architecture multi-agents, un enquêteur par signal)."
    )

    detail = pd.DataFrame(
        [m | {"run": i + 1} for r in base["alertes"].values() for i, m in enumerate(r["mesures"])]
    )
    with st.expander("Détail des exécutions"):
        st.dataframe(detail, hide_index=True, width="stretch")


def onglet_donnees() -> None:
    df = transactions()
    st.markdown(f"**{len(CLIENTS)} clients · {len(df)} transactions** du {df.date.min():%d/%m/%Y} au {df.date.max():%d/%m/%Y}")
    st.dataframe(pd.DataFrame(CLIENTS.values()), hide_index=True, width="stretch")

    id_client = st.selectbox(
        "Client", list(CLIENTS), index=2, format_func=lambda i: f"{i} · {CLIENTS[i]['nom']}"
    )
    du_client = df[df.client_id == id_client]
    mensuel = (
        du_client.assign(mois=du_client.date.dt.to_period("M").dt.to_timestamp())
        .pivot_table(index="mois", columns="sens", values="montant", aggfunc="sum", fill_value=0)
    )
    st.markdown("Flux mensuels (€)")
    st.bar_chart(mensuel, stack=False)
    st.dataframe(
        du_client.sort_values("date", ascending=False),
        hide_index=True,
        width="stretch",
        column_config={"date": st.column_config.DateColumn(format="DD/MM/YYYY")},
    )


# --- Page -----------------------------------------------------------------------------------
st.title("🔎 Agent d'enquête anti-blanchiment")
st.markdown(
    "Un agent LLM instruit des alertes LCB-FT ; **un code déterministe vérifie ses preuves et décide**. "
    "Données synthétiques tirées d'un cas réel du rapport Tracfin 2024-2025."
)
enquete, projet, evaluation, explorer = st.tabs(
    ["🔎 Enquête", "📖 Le projet", "📊 Évaluation", "🗂️ Données"]
)
with enquete:
    onglet_enquete()
with projet:
    onglet_projet()
with evaluation:
    onglet_evaluation()
with explorer:
    onglet_donnees()
