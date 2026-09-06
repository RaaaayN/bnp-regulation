# Architecture

## Objectif et principes

Regulatory Intelligence Assistant aide un analyste à détecter un changement
réglementaire, à retrouver les politiques et contrôles potentiellement concernés,
puis à produire une analyse sourcée. Il s'agit d'un outil d'aide à la décision :
il ne rend pas d'avis juridique et ne prend aucune décision de conformité.

Les principes structurants sont les suivants :

- aucune conclusion importante sans preuve traçable ;
- le contenu documentaire est traité comme une donnée non fiable, jamais comme
  une instruction adressée au modèle ;
- les impacts sont qualifiés de potentiels jusqu'à validation humaine ;
- PostgreSQL/pgvector porte le corpus et la recherche sémantique, tandis que
  FalkorDB porte les relations métier ;
- les composants spécialisés restent orchestrés et vérifiés plutôt que de former
  une chaîne d'agents autonomes sans contrôle.

## Vue conteneurs du MVP

```mermaid
flowchart LR
    Analyste[Analyste conformité] -->|HTTP / JSON| API[FastAPI]
    API -->|SQL + recherche vectorielle| PG[(PostgreSQL + pgvector)]
    API -->|Cypher sur protocole Redis| Graph[(FalkorDB)]
    Sources[EBA / ECB / EUR-Lex] -.->|ingestion planifiée, cible MVP| API
    API -.->|requêtes contrôlées, cible MVP| LLM[Fournisseur LLM]
```

Le déploiement Docker local fournit aujourd'hui trois services : `api`,
`postgres` et `falkordb`. L'endpoint `GET /health` est une sonde de vivacité de
l'API. Il ne constitue pas encore une sonde de disponibilité complète des bases.

## Composants applicatifs cibles

```mermaid
flowchart TB
    HTTP[API FastAPI] --> Orchestrator[Orchestrateur]
    Orchestrator --> Retrieval[Retrieval]
    Orchestrator --> Change[Analyse de changement]
    Orchestrator --> Impact[Analyse d'impact]
    Retrieval --> PG[(Corpus + vecteurs)]
    Change --> PG
    Impact --> KG[(Knowledge graph)]
    Retrieval --> Reviewer[Reviewer]
    Change --> Reviewer
    Impact --> Reviewer
    Reviewer --> Guard{Preuve suffisante ?}
    Guard -->|oui| Answer[Réponse citée]
    Guard -->|non| Refusal[INSUFFICIENT EVIDENCE]
```

| Composant | Responsabilité | État |
|---|---|---|
| API | Contrat HTTP, validation, cycle de vie | Socle implémenté |
| Ingestion | Parsing, structure, métadonnées, chunking sémantique | Cible MVP |
| Retrieval | Recherche hybride, reranking, seuil de preuve | Cible MVP |
| Change analysis | Alignement de sections et classification sémantique | Cible MVP |
| Impact analysis | Parcours exigences → politiques → contrôles → processus | Cible MVP |
| Reviewer | Vérification claim → source et suppression des claims non supportés | Cible MVP |
| PostgreSQL/pgvector | Documents, passages, embeddings, métadonnées, audit | Infrastructure prête |
| FalkorDB | Relations réglementaires et internes | Infrastructure prête |

## Flux principal

```mermaid
sequenceDiagram
    actor U as Analyste
    participant A as API / Orchestrateur
    participant P as PostgreSQL/pgvector
    participant G as FalkorDB
    participant M as LLM
    participant R as Reviewer

    U->>A: Compare V1 et V2
    A->>P: Charge sections et métadonnées
    P-->>A: Passages versionnés
    A->>M: Compare les sections avec contexte délimité
    M-->>A: Changements structurés + claims
    A->>G: Recherche politiques et contrôles liés
    G-->>A: Chemins d'impact potentiels
    A->>R: Claims, preuves et chemins
    R-->>A: supported / partial / unsupported
    A-->>U: Analyse citée ou preuve insuffisante
```

L'ingestion conserve l'identité du document, sa version, l'article, la section,
la page et le passage d'origine. Une citation renvoie à ces éléments immuables ;
un embedding ou une réponse générée ne remplace jamais la source.

## Décisions d'architecture

### Deux stockages spécialisés

Le texte, ses métadonnées et ses vecteurs ont un modèle relationnel naturel et
bénéficient des transactions de PostgreSQL. Les dépendances entre exigences,
politiques, contrôles, processus et équipes se parcourent plus naturellement dans
un graphe. Le coût opérationnel de deux bases est accepté afin d'éviter de forcer
un seul modèle de données à servir deux usages différents.

### Orchestration explicite

Les composants Retrieval, Change, Impact et Reviewer ont des entrées/sorties
structurées. L'orchestrateur garde le contrôle du flux, des délais, des budgets et
des erreurs. Cette approche rend les décisions testables et auditables.

### Refus fondé sur le niveau de preuve

Le seuil de retrieval est configurable. En dessous du seuil, ou lorsqu'un claim
n'est pas soutenu par son passage, la réponse doit expliciter l'insuffisance de
preuve. La confiance du modèle n'est pas assimilée à une probabilité juridique.

### Déploiement reproductible

L'API est construite en image multi-stage et exécutée par un utilisateur non-root.
Compose initialise les dépendances, attend leurs healthchecks et conserve les
données dans des volumes nommés.

## Sécurité et gouvernance

- Authentification et RBAC doivent précéder l'exposition à plusieurs profils.
- Les documents récupérés sont délimités et neutralisés contre la prompt injection.
- Les secrets ne sont ni placés dans l'image ni versionnés ; ils proviennent de
  l'environnement ou, en production, d'un gestionnaire de secrets.
- Les données personnelles doivent être détectées et masquées avant tout appel à
  un fournisseur LLM externe.
- Le journal d'audit doit inclure utilisateur, requête, passages récupérés,
  versions de prompt et de modèle, réponse, citations et décision humaine.
- Les communications inter-services doivent être chiffrées et authentifiées en
  production. Les ports de base exposés par Compose servent uniquement au
  développement local.
- Les rétentions, sauvegardes, restaurations et suppressions doivent suivre la
  classification des données de l'organisation.

## Limites actuelles

- Le socle actuel expose une vivacité, sans readiness applicative des bases.
- FalkorDB est démarré mais son client n'est pas encore intégré à l'API.
- L'image FalkorDB utilise le tag `latest` pour le MVP local ; un digest immuable
  doit être fixé avant une mise en production.
- Compose fournit un environnement mono-hôte sans TLS, haute disponibilité,
  sauvegarde automatisée ni rotation de secrets.
- L'ingestion, le retrieval, le graphe métier, les agents, l'évaluation et
  l'interface utilisateur restent des composants cibles.
- Aucune métrique de qualité ne doit être revendiquée avant évaluation sur un jeu
  de référence versionné.
