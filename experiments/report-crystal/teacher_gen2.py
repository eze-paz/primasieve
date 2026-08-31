"""Program-teacher v2: rich, LONGER, qualitative narratives (Resum + Observacions).

Output gold = the two narrative sections ONLY (no digits). The full report is
assembled at eval time by render.assemble(), which owns all numbers. Narratives
are 3-5 sentences each and data-conditional (level trend, consumption, alarm
status, comms) so the crystal learns a mapping, not one template.

  py -3.12 teacher_gen2.py --n 240 --out gold2.jsonl
"""
from __future__ import annotations
import argparse, json, random
import gen_data, render

NUMWORD = {0: "cap", 1: "una", 2: "dues", 3: "tres", 4: "quatre", 5: "cinc"}


def _trend(t):
    d = t["nivell_pct_final"] - t["nivell_pct_inici"]
    if d <= -30: return "una davallada pronunciada"
    if d <= -10: return "un descens moderat"
    if d < 0: return "un lleuger descens"
    if d < 10: return "un nivell estable"
    return "una recarrega"


def resum(inp, r):
    site, city = inp["instalacio"], inp["poblacio"]
    ntanks = len(inp["tancs"])
    al = inp["alarmes"]
    pend = [a for a in al if not a["resolta"]]
    s = []
    s.append(r.choice([
        "Durant aquesta setmana, la instalacio %s de %s ha operat amb %s tancs monitoritzats." % (site, city, NUMWORD.get(ntanks, str(ntanks))),
        "Informe de seguiment setmanal de la instalacio %s, situada a %s, amb %s tancs actius." % (site, city, NUMWORD.get(ntanks, str(ntanks))),
        "Aquesta setmana la instalacio %s (%s) ha mantingut el seu funcionament habitual." % (site, city),
    ]))
    trends = [_trend(t) for t in inp["tancs"]]
    if any("davallada" in x or "descens moderat" in x for x in trends):
        s.append(r.choice([
            "S'ha observat un consum destacat en algun dels tancs, amb una reduccio notable del nivell disponible.",
            "El comportament dels nivells reflecteix una demanda elevada en part del periode.",
        ]))
    else:
        s.append(r.choice([
            "Els nivells dels tancs s'han mantingut dins dels marges esperats al llarg del periode.",
            "El comportament dels tancs ha estat estable, sense variacions brusques.",
        ]))
    if not al:
        s.append(r.choice([
            "No s'ha registrat cap alarma, la qual cosa indica un funcionament correcte del sistema.",
            "El periode s'ha tancat sense incidencies ni alarmes actives.",
        ]))
    elif pend:
        s.append(r.choice([
            "Cal destacar que s'han produit %s alarmes, algunes de les quals resten pendents de resolucio." % NUMWORD.get(len(al), str(len(al))),
            "S'han registrat %s alarmes durant la setmana i alguna continua oberta, fet que requereix atencio." % NUMWORD.get(len(al), str(len(al))),
        ]))
    else:
        s.append(r.choice([
            "S'han gestionat %s alarmes al llarg de la setmana, totes resoltes satisfactoriament." % NUMWORD.get(len(al), str(len(al))),
            "Tot i registrar-se %s alarmes, totes han quedat resoltes dins del periode." % NUMWORD.get(len(al), str(len(al))),
        ]))
    return " ".join(s)


def observacions(inp, r):
    obs = []
    for t in inp["tancs"]:
        if t["nivell_pct_final"] < 30:
            obs.append(r.choice([
                "Es recomana programar el reompliment del tanc %s a curt termini, ja que ha finalitzat la setmana amb un nivell baix." % t["id"],
                "El tanc %s presenta un nivell final reduit; convindria planificar-ne el subministrament abans que arribi a valors critics." % t["id"],
            ]))
        if t["consum_m3"] > 1500:
            obs.append(r.choice([
                "El consum del tanc %s ha estat elevat; seria recomanable revisar la demanda del proces associat." % t["id"],
                "Convindria analitzar el consum del tanc %s, superior a l'habitual, per descartar fuites o ineficiencies." % t["id"],
            ]))
    for a in inp["alarmes"]:
        if not a["resolta"]:
            obs.append(r.choice([
                "L'alarma de %s al tanc %s continua oberta i requereix intervencio del servei tecnic com abans millor." % (a["tipus"], a["tanc"]),
                "Es prioritari fer seguiment de l'alarma de %s del tanc %s, encara pendent de resolucio." % (a["tipus"], a["tanc"]),
            ]))
        if a["code"] == "comms_loss":
            obs.append(r.choice([
                "Es recomana revisar l'equip de comunicacions i la connectivitat de la telemetria per evitar noves caigudes de senyal.",
                "Convindria comprovar l'estat del sistema de comunicacions, ja que s'ha detectat una perdua de connexio.",
            ]))
    if not obs:
        obs.append(r.choice([
            "No es detecten incidencies rellevants; es recomana mantenir el pla de manteniment preventiu habitual.",
            "L'estat general es satisfactori. Nomes cal continuar amb el seguiment rutinari de la instalacio.",
        ]))
    obs.append(r.choice([
        "Es continuara monitoritzant l'evolucio dels parametres durant la propera setmana.",
        "El proper informe recollira l'evolucio d'aquests indicadors.",
    ]))
    return " ".join(obs[:4])


def make_narrative(inp, seed):
    r = random.Random(seed)
    return "## Resum\n%s\n\n## Observacions i recomanacions\n%s" % (
        resum(inp, r), observacions(inp, r))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="gold2.jsonl")
    a = ap.parse_args()
    import evalr2
    rng = random.Random(a.seed)
    kept = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for i in range(a.n):
            inp = gen_data.gen_input(rng)
            narr = make_narrative(inp, a.seed * 99991 + i)
            resum_t, obs_t = render.split_narrative(narr)
            full = render.assemble(inp, resum_t, obs_t)
            s = evalr2.score_report(inp, full, narr)
            if s["numbers"] == 1.0 and s["alarms"] == 1.0 and s["narr_clean"] == 1.0 and s["catalan"] >= 0.9:
                f.write(json.dumps({"input": inp, "narrative": narr}, ensure_ascii=False) + "\n")
                kept += 1
            else:
                print("reject %d: %s" % (i, s))
    print("kept %d/%d -> %s" % (kept, a.n, a.out))
