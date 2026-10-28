"""Inventaire des conteneurs Docker et de l'instance NetBox.

Lit la configuration dans l'environnement (DOCKER_API_URL, NETBOX_URL,
NETBOX_TOKEN), relève l'état des conteneurs et un résumé NetBox, écrit le tout
dans inventaire.json et affiche un résumé lisible. Sort en erreur, avec un code
de retour non nul, si un service est injoignable.
"""

import os
import sys
import json
from datetime import datetime

import requests

DOCKER = os.environ.get("DOCKER_API_URL", "http://127.0.0.1:2375")
NETBOX = os.environ.get("NETBOX_URL", "http://127.0.0.1:8080")
NETBOX_TOKEN = os.environ.get("NETBOX_TOKEN", "")

session = requests.Session()


def inventaire_docker():
    """Liste tous les conteneurs ; mesure CPU et mémoire de ceux qui tournent."""
    reponse = session.get(f"{DOCKER}/containers/json?all=true", timeout=10)
    reponse.raise_for_status()

    conteneurs = []
    for c in reponse.json():
        infos = {
            "nom": c["Names"][0].lstrip("/"),
            "image": c["Image"],
            "etat": c["State"],
        }
        if c["State"] == "running":
            stats = session.get(
                f"{DOCKER}/containers/{c['Id']}/stats?stream=false", timeout=10
            ).json()
            cpu, avant = stats["cpu_stats"], stats["precpu_stats"]
            delta_cpu = cpu["cpu_usage"]["total_usage"] - avant["cpu_usage"]["total_usage"]
            delta_sys = cpu.get("system_cpu_usage", 0) - avant.get("system_cpu_usage", 0)
            coeurs = cpu.get("online_cpus", 1)
            infos["cpu"] = round(delta_cpu / delta_sys * coeurs * 100, 2) if delta_sys else 0.0
            infos["memoire_mo"] = round(stats["memory_stats"]["usage"] / 1024 / 1024, 1)
        conteneurs.append(infos)
    return conteneurs


def inventaire_netbox():
    """Version de NetBox et nombre de types d'objets, en suivant la pagination."""
    entetes = {"Authorization": f"Bearer {NETBOX_TOKEN}", "Accept": "application/json"}

    statut = session.get(f"{NETBOX}/api/status/", headers=entetes, timeout=10)
    statut.raise_for_status()

    url = f"{NETBOX}/api/core/object-types/?limit=50"
    types = 0
    while url:
        page = session.get(url, headers=entetes, timeout=10)
        page.raise_for_status()
        page = page.json()
        types += len(page["results"])
        url = page["next"]

    return {"version": statut.json()["netbox-version"], "types_objets": types}


try:
    conteneurs = inventaire_docker()
except requests.RequestException as erreur:
    sys.exit(f"API Docker injoignable sur {DOCKER} : {erreur}")

try:
    netbox = inventaire_netbox()
except requests.RequestException as erreur:
    sys.exit(f"NetBox injoignable sur {NETBOX} : {erreur}")

inventaire = {
    "date": datetime.now().isoformat(timespec="seconds"),
    "conteneurs": conteneurs,
    "netbox": netbox,
}

with open("inventaire.json", "w", encoding="utf-8") as f:
    json.dump(inventaire, f, indent=2, ensure_ascii=False)

print(f"Relevé du {inventaire['date']} — {len(conteneurs)} conteneurs")
for c in conteneurs:
    if c["etat"] == "running":
        print(f"  {c['nom']:35} {c['cpu']:>6} %   {c['memoire_mo']:>8} Mo")
    else:
        print(f"  {c['nom']:35} {c['etat']}")
print(f"NetBox {netbox['version']} — {netbox['types_objets']} types d'objets")
