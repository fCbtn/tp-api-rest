# TP1 : exploration des API Docker et NetBox

## Préparation

```bash
docker run -d --name web1 --label adminapi.managed=true nginx:alpine
docker run -d --name intrus nginx:alpine
```

`web1` porte le label `adminapi.managed=true`, `intrus` non.

## API Docker

```bash
D=http://127.0.0.1:2375
```

| Commande | Code | Constat |
|---|---|---|
| `curl -s $D/version` | 200 | Docker Engine 29.7.2, API 1.55 |
| `curl -s "$D/containers/json?all=true"` | 200 | tous les conteneurs de la machine, démarrés ou non, y compris ceux d'autres projets |
| `curl -s --get $D/containers/json --data-urlencode 'all=true' --data-urlencode 'filters={"label":["adminapi.managed=true"]}'` | 200 | seul `web1` apparaît : le filtre par label est appliqué par Docker |
| `curl -s $D/containers/web1/json` | 200 | détail du conteneur : `Name` (`/web1`), `State.Status`, `Config.Image`, `Config.Labels` |
| `curl -s -o /dev/null -w "%{http_code}\n" -X POST $D/containers/web1/stop` | 204 | conteneur arrêté, réponse sans corps |
| la même commande, une seconde fois | 304 | déjà arrêté : rien n'a changé |
| `curl -s -o /dev/null -w "%{http_code}\n" $D/containers/fantome/json` | 404 | conteneur inconnu |

## API NetBox

```bash
N=http://127.0.0.1:8080/api
```

| Commande | Code | Constat |
|---|---|---|
| `curl -s -X POST $N/users/tokens/provision/ -H "Content-Type: application/json" -H "Accept: application/json" -d '{"username": "admin", "password": "admin"}'` | 201 | token créé ; la réponse donne `key` et `token`, le token complet s'écrit `nbt_<key>.<token>` |

Le token est rangé dans `.env` (`NETBOX_TOKEN=nbt_<key>.<token>`, fichier dans .gitignore), puis
chargé dans le terminal :

```bash
set -a; source .env; set +a
A="Authorization: Bearer $NETBOX_TOKEN"
```

| Commande | Code | Constat |
|---|---|---|
| `curl -s -H "$A" $N/status/` | 200 | NetBox 4.7.3 répond, le token est accepté |
| `curl -s -X POST $N/virtualization/cluster-types/ -H "$A" -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name": "Docker", "slug": "docker"}'` | 201 | type de cluster `Docker` créé (id 1) |
| `curl -s -X POST $N/virtualization/clusters/ -H "$A" -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name": "docker-local", "type": 1}'` | 201 | cluster `docker-local` créé (id 1), statut `active`, visible dans l'interface NetBox |
