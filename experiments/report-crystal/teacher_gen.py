"""Program-teacher: gold Catalan reports from telemetry JSON, varied phrasing.

Every generated report is verified against evalr (structure=1, num_cov=1,
alarms=1, catalan high) before it enters the dataset — clean labels (the
c_gold lesson from the distill experiment: label noise taxes binding).

Variation: seeded choice among phrasing variants per section + data-conditional
narrative in Resum/Observacions (consumption level, unresolved alarms, comms
loss, low final level), so the student learns a mapping, not one template.

  py -3.12 teacher_gen.py --n 200 --out gold.jsonl
"""
from __future__ import annotations
import argparse, json, random
import gen_data, evalr


def _fmt_tank(t, r: random.Random):
    v = r.choice([
        "- {id} ({gas}): nivell del {ni}% al {nf}%, pressio mitjana {p} bar, temperatura mitjana {tc} C, consum {c} m3.",
        "- {id} ({gas}): el nivell ha passat del {ni}% al {nf}%; pressio mitjana de {p} bar, temperatura mitjana de {tc} C i consum de {c} m3.",
        "- Tanc {id} de {gas}: nivell inicial {ni}%, nivell final {nf}%, pressio mitjana {p} bar, temperatura mitjana {tc} C, consum setmanal {c} m3.",
    ])
    return v.format(id=t["id"], gas=t["gas"], ni=t["nivell_pct_inici"],
                    nf=t["nivell_pct_final"], p=t["pressio_bar_mitjana"],
                    tc=t["temp_c_mitjana"], c=int(t["consum_m3"]))


def _fmt_alarm(a, r: random.Random):
    est = "Resolta." if a["resolta"] else "Pendent de resolucio."
    v = r.choice([
        "- Alarma de {tipus} al tanc {tanc} ({dia}, {dur} min). {est}",
        "- {dia}: alarma de {tipus} al tanc {tanc}, durada {dur} min. {est}",
    ])
    return v.format(tipus=a["tipus"], tanc=a["tanc"], dia=a["dia"].capitalize()
                    if v.startswith("- {dia}") else a["dia"],
                    dur=a["durada_min"], est=est)


def _resum(inp, r: random.Random):
    n_al = len(inp["alarmes"])
    pend = [a for a in inp["alarmes"] if not a["resolta"]]
    frases = []
    frases.append(r.choice([
        "Setmana %d a la instalacio %s de %s." % (inp["setmana"], inp["instalacio"], inp["poblacio"]),
        "Informe corresponent a la setmana %d de la instalacio %s (%s)." % (inp["setmana"], inp["instalacio"], inp["poblacio"]),
    ]))
    if n_al == 0:
        frases.append(r.choice([
            "Funcionament correcte durant tota la setmana, sense incidencies.",
            "Tots els parametres s'han mantingut dins dels marges habituals.",
        ]))
    elif pend:
        frases.append(r.choice([
            "S'han registrat %d alarmes, i alguna resta pendent de resolucio." % n_al,
            "Setmana amb %d alarmes registrades; cal atencio a les que continuen obertes." % n_al,
        ]))
    else:
        frases.append(r.choice([
            "S'han registrat %d alarmes, totes resoltes correctament." % n_al,
            "Hi ha hagut %d alarmes durant la setmana, ja resoltes." % n_al,
        ]))
    return " ".join(frases)


def _observacions(inp, r: random.Random):
    obs = []
    for t in inp["tancs"]:
        if t["nivell_pct_final"] < 30:
            obs.append(r.choice([
                "El tanc %s ha acabat la setmana amb un nivell baix; es recomana programar el proper subministrament aviat." % t["id"],
                "Cal planificar el reompliment del tanc %s, que presenta un nivell final reduit." % t["id"],
            ]))
        if t["consum_m3"] > 1500:
            obs.append(r.choice([
                "El consum del tanc %s ha estat elevat aquesta setmana." % t["id"],
                "Es constata un consum alt al tanc %s; convindria revisar la demanda del proces." % t["id"],
            ]))
    for a in inp["alarmes"]:
        if not a["resolta"]:
            obs.append(r.choice([
                "L'alarma de %s del tanc %s continua oberta i cal fer-ne seguiment." % (a["tipus"], a["tanc"]),
                "Resta pendent l'alarma de %s al tanc %s; es recomana intervencio del servei tecnic." % (a["tipus"], a["tanc"]),
            ]))
        if a["code"] == "comms_loss":
            obs.append(r.choice([
                "Es recomana revisar l'equip de comunicacions per evitar noves caigudes.",
                "Convindria comprovar la connexio del sistema de telemetria.",
            ]))
    if not obs:
        obs.append(r.choice([
            "No hi ha observacions rellevants; es recomana mantenir el pla de manteniment habitual.",
            "Sense observacions destacables. Seguiment normal de la instalacio.",
        ]))
    return " ".join(obs[:3])


def make_report(inp, seed):
    r = random.Random(seed)
    parts = ["# Informe setmanal - %s (setmana %d)" % (inp["instalacio"], inp["setmana"]), ""]
    parts += ["## Resum", _resum(inp, r), ""]
    parts += ["## Estat dels tancs"] + [_fmt_tank(t, r) for t in inp["tancs"]] + [""]
    parts.append("## Alarmes")
    if inp["alarmes"]:
        parts += [_fmt_alarm(a, r) for a in inp["alarmes"]]
    else:
        parts.append("Sense alarmes registrades.")
    parts.append("")
    parts += ["## Observacions i recomanacions", _observacions(inp, r)]
    return "\n".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="gold.jsonl")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    kept, tries = 0, 0
    with open(a.out, "w", encoding="utf-8") as f:
        while kept < a.n and tries < a.n * 3:
            tries += 1
            inp = gen_data.gen_input(rng)
            rep = make_report(inp, seed=a.seed * 100000 + tries)
            s = evalr.score_report(inp, rep)
            if s["structure"] == 1.0 and s["num_cov"] == 1.0 and s["alarms"] == 1.0 and s["catalan"] >= 0.9:
                f.write(json.dumps({"input": inp, "report": rep}, ensure_ascii=False) + "\n")
                kept += 1
            else:
                print("rejected (try %d): %s" % (tries, s))
    print("kept %d/%d gold reports -> %s" % (kept, tries, a.out))
