"""Synthetic gas-site telemetry inputs for the Catalan report crystal.

Each input is a JSON dict a monitoring backend (modbus-poller style) could
emit for a weekly period: site, gas tanks with level/pressure/temperature
readings, consumption, and alarm events. The report model must render a
fixed-section Catalan report whose every number comes from this JSON.
"""
from __future__ import annotations
import json, random, argparse

SITES = [
    ("Planta Igualada", "Igualada"), ("Hospital de Vic", "Vic"),
    ("Celler Vilafranca", "Vilafranca del Penedes"), ("Planta Manresa", "Manresa"),
    ("Laboratori Girona", "Girona"), ("Envasadora Reus", "Reus"),
    ("Hospital de Terrassa", "Terrassa"), ("Planta Figueres", "Figueres"),
]
GASES = ["N2", "O2", "CO2", "Ar"]
ALARM_TYPES = [
    ("nivell baix", "low_level"), ("pressio alta", "high_pressure"),
    ("caiguda de comunicacions", "comms_loss"), ("temperatura alta", "high_temp"),
]

def gen_input(rng: random.Random):
    site, city = rng.choice(SITES)
    week = rng.randint(1, 52)
    tanks = []
    for i in range(rng.randint(1, 3)):
        gas = rng.choice(GASES)
        tanks.append({
            "id": "T%d" % (i + 1), "gas": gas,
            "nivell_pct_inici": round(rng.uniform(35, 95), 1),
            "nivell_pct_final": round(rng.uniform(15, 90), 1),
            "pressio_bar_mitjana": round(rng.uniform(2.0, 18.0), 1),
            "temp_c_mitjana": round(rng.uniform(-190, 25), 1),
            "consum_m3": round(rng.uniform(50, 2400), 0),
        })
    alarms = []
    for _ in range(rng.randint(0, 3)):
        at, code = rng.choice(ALARM_TYPES)
        alarms.append({
            "tipus": at, "code": code,
            "tanc": rng.choice(tanks)["id"],
            "dia": rng.choice(["dilluns", "dimarts", "dimecres", "dijous",
                               "divendres", "dissabte", "diumenge"]),
            "durada_min": rng.randint(3, 240),
            "resolta": rng.random() < 0.8,
        })
    return {"instalacio": site, "poblacio": city, "setmana": week,
            "tancs": tanks, "alarmes": alarms}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="inputs.jsonl")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    with open(a.out, "w", encoding="utf-8") as f:
        for _ in range(a.n):
            f.write(json.dumps(gen_input(rng), ensure_ascii=False) + "\n")
    print("wrote", a.n, "inputs to", a.out)
