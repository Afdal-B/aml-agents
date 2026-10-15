# Données de simulation : cas n°13 du rapport Tracfin

## Source

Tracfin, *LCB-FT : état de la menace 2024-2025* (tome 3 du rapport d'activité 2024), publié le 29/09/2025.
Cas n°13, « Détournement de fonds publics via une association », page 38.
PDF : https://www.economie.gouv.fr/files/files/directions_services/tracfin/media-document/TRACFIN_2024_Tome3_FR_WEB_0.pdf
Licence : le site de publication indique la Licence Ouverte Etalab 2.0 (à relire avant toute publication).

Les données sont **synthétiques**. Les noms de personnes, d'associations et de commerces sont fictifs.

## Ce qui vient du rapport, inchangé

| Élément du rapport | Où le retrouver |
|---|---|
| Association financée exclusivement par des subventions de collectivités, 400 k€ deux années de suite (800 k€) | `contreparties.json` |
| 600 k€ transférés vers les comptes personnels du couple (le rapport les présente comme la quasi-totalité des fonds) | 12 virements, somme exacte de 600 000 € |
| Retraits en espèces pour 200 k€ | 40 retraits, somme exacte de 200 000 € |
| Achats de biens de luxe (bijoux, montres, habits) pour 50 k€ | 9 paiements par carte, somme exacte de 50 000 € |
| Un bien immobilier pour 200 k€ | 1 virement au notaire de 200 000 € |
| Voyages pour 50 k€ | 8 paiements par carte, somme exacte de 50 000 € |
| Monsieur président, Madame bénévole permanente | `situation_declaree` du client CLI-003 |
| Seuls les revenus de l'activité professionnelle du couple sont déclarés | `situation_declaree`, et avis d'imposition égal à 12 fois le revenu mensuel déclaré |
| Pas de commissaire aux comptes ni de publication des comptes, malgré des subventions au-dessus de 153 k€ | `contreparties.json` |
| Les cinq critères d'alerte | `signaux.json`, mot pour mot |

## Ce que le rapport ne dit pas et que j'ai ajouté

| Ajout | Pourquoi |
|---|---|
| Calendrier (1er oct. 2024 au 30 sept. 2026), nombre et montants unitaires des opérations | Il faut des transactions datées. Seules les **sommes** sont celles du rapport |
| Noms fictifs, commerces, employeurs, notaire | Idem |
| Revenus du couple (3 400 €/mois, avis d'imposition 40 800 €), patrimoine déclaré (18 000 €), soldes initiaux | Le rapport dit seulement que les dépenses sont incohérentes avec la situation professionnelle et le patrimoine déclaré |
| Les deux conjoints regroupés en un seul compte joint (CLI-003) | Le rapport parle de comptes personnels sans donner de répartition : je n'en invente pas |
| Les 100 k€ restants (600 k€ reçus moins 500 k€ dépensés) laissés sur le compte | Le rapport ne dit pas où ils vont |
| Règle d'alerte R1 | Voir plus bas |
| **Sosie légitime (CLI-005)** | Absent du rapport : il fournit le faux positif |
| 4 clients de bruit (CLI-001, 002, 004, 006) et des opérations courantes pour tous | Pour que chaque outil ait à filtrer |

Le couple n'a aucun petit retrait d'espèces : tous ses retraits sont ceux du rapport.

## Règle d'alerte R1 (ajoutée)

Crédits cumulés provenant d'une même contrepartie supérieurs à 15 000 € sur 90 jours glissants, évalués à la revue du 30/09/2026.
Elle est **calculée sur les transactions**, pas écrite à la main, et alerte exactement deux clients :

| Alerte | Client | Contrepartie | Cumul sur 90 jours |
|---|---|---|---|
| ALT-001 | CLI-003 | Association caritative | 150 300 € |
| ALT-002 | CLI-005 | Association socio-culturelle | 15 300 € |

La règle seule ne les distingue pas : c'est l'enquête qui fait la différence.

## Fichiers

| Fichier | Contenu | Lu par |
|---|---|---|
| `clients.json` | Profil, revenus, avis d'imposition, patrimoine, situation déclarée, solde initial | Outil profil |
| `transactions.json` | 2 363 opérations : id, client, date, montant, sens, mode, libellé, contrepartie, pays | Outil historique |
| `contreparties.json` | Type et informations publiques de chaque contrepartie | Outil contreparties |
| `signaux.json` | Liste fermée de signaux : les critères d'alerte du cas | Format `Constat` |
| `alertes.json` | Les deux alertes, sans étiquette de vérité | Les agents |
| `verite.json` | Verdict, signaux attendus et transactions-preuves | `evaluer.py` uniquement |

Régénération : `python scripts/generer.py`. Vérification : `pytest tests`.
