# Déploiement

## Prérequis

- Docker Engine récent avec le plugin Compose v2 ;
- au moins 4 Go de mémoire disponible pour les trois conteneurs ;
- ports 8000, 5432 et 6379 disponibles, ou remplacés dans `.env`.

## Démarrage local

```bash
cp .env.example .env
docker compose config
docker compose up --build --detach --wait
curl --fail http://localhost:8000/health
```

La documentation OpenAPI est disponible sur `http://localhost:8000/docs`.
`docker compose ps` affiche l'état des sondes et `docker compose logs --follow`
suit les journaux.

Les mêmes opérations sont exposées par le Makefile :

```bash
make docker-up
make docker-ps
make docker-logs
```

## Configuration

Compose lit automatiquement le fichier `.env` placé à la racine. Les paramètres
utiles sont documentés dans `.env.example`.

| Variable | Valeur locale | Rôle |
|---|---|---|
| `API_PORT` | `8000` | Port publié de l'API |
| `RIA_ENVIRONMENT` | `development` | Nom d'environnement applicatif |
| `RIA_LOG_LEVEL` | `INFO` | Niveau de journalisation |
| `RIA_EVIDENCE_THRESHOLD` | `0.15` | Seuil minimal de preuve |
| `RIA_MAX_RESULTS` | `5` | Nombre maximal de résultats |
| `POSTGRES_*` | voir exemple | Base, utilisateur, mot de passe et port PostgreSQL |
| `FALKORDB_PORT` | `6379` | Port FalkorDB publié localement |

La chaîne `RIA_DATABASE_URL` est assemblée par Compose avec les variables
`POSTGRES_*`. Le conteneur reçoit également `FALKORDB_URL`; l'application ne la
consommera qu'après intégration du client graphe.

## Cycle de vie et données

```bash
# Arrêt en conservant PostgreSQL et FalkorDB
docker compose down

# Suppression explicite des conteneurs ET des volumes de données
docker compose down --volumes
```

La seconde commande est destructive. Pour une sauvegarde exploitable, utiliser
`pg_dump` pour PostgreSQL et une stratégie RDB/AOF validée pour FalkorDB avant de
supprimer ou remplacer les volumes.

## Diagnostic

```bash
docker compose ps
docker compose logs api
docker compose logs postgres
docker compose logs falkordb
```

- API `unhealthy` : vérifier les logs et appeler `/health` depuis le conteneur.
- PostgreSQL `unhealthy` : vérifier les valeurs `POSTGRES_*` et l'espace disque.
- FalkorDB `unhealthy` : vérifier que `redis-cli ping` retourne `PONG`.
- Port déjà occupé : changer `API_PORT`, `POSTGRES_PORT` ou `FALKORDB_PORT` dans
  `.env`, puis recréer la stack.

## Passage en production

Le fichier Compose est une référence locale, pas une plateforme de production.
Avant tout déploiement manipulant des documents internes :

1. fixer chaque image par version et digest, puis scanner les vulnérabilités ;
2. fournir les secrets via le gestionnaire de secrets de la plateforme ;
3. ne pas publier directement les ports PostgreSQL et FalkorDB ;
4. placer l'API derrière un reverse proxy TLS avec authentification et RBAC ;
5. ajouter des probes de readiness qui testent les dépendances ;
6. définir limites CPU/mémoire, réplication, sauvegardes et tests de restauration ;
7. centraliser logs, métriques et traces sans exposer de contenu sensible ;
8. appliquer migrations de schéma et procédures de rollback avant le trafic ;
9. vérifier résidence, classification, rétention et transfert des données vers le
   fournisseur LLM ;
10. conserver une validation humaine pour toute conclusion réglementaire.

Le build de l'API est reproductible avec `docker build -t regulatory-api .`. Le
même artefact doit être promu entre environnements ; seule sa configuration doit
changer.
