import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from aml_agents.schema import Alerte, Client, Constat, Contrepartie, Signal, Transaction

DONNEES = Path(__file__).resolve().parents[1] / "data"


def charger(nom):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))


def test_donnees_se_chargent():
    assert len([Transaction(**t) for t in charger("transactions.json")]) == 2363
    assert len([Client(**c) for c in charger("clients.json")]) == 6
    assert [Contrepartie(**c) for c in charger("contreparties.json")]
    assert len([Alerte(**a) for a in charger("alertes.json")]) == 2


def test_transaction_invalide_rejetee():
    base = charger("transactions.json")[0]
    with pytest.raises(ValidationError):
        Transaction(**{**base, "montant": -5})
    with pytest.raises(ValidationError):
        Transaction(**{**base, "sens": "inconnu"})


def test_signal_invente_rejete():
    with pytest.raises(ValidationError):
        Constat(signal="signal_invente", preuves=["TX-000001"], explication="x")


def test_constat_sans_preuve_rejete():
    with pytest.raises(ValidationError):
        Constat(signal="retraits_especes_importants", preuves=[], explication="x")


def test_signaux_egaux_au_fichier():
    assert set(get_args(Signal)) == {s["id"] for s in charger("signaux.json")}
