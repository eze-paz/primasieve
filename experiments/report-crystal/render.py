"""Hybrid renderer: CODE owns every number, the crystal owns only the prose.

The full report is assembled as:
    # Informe setmanal ...        (template)
    ## Resum                      (CRYSTAL narrative, qualitative)
    ## Estat dels tancs           (template table, computed deltas)
    ## Alarmes                    (template list, ALL alarms)
    ## Observacions i recomanacions (CRYSTAL narrative, qualitative)

Because tank readings and alarm facts are rendered from JSON by code, number
fidelity and alarm coverage are 100% by construction. The crystal never emits a
figure; its output is the two narrative blocks only.
"""
from __future__ import annotations
import re

# Instruction for the crystal: narrative-only, qualitative, no digits.
INSTR_NARR = (
    "Ets el redactor d'informes de GasN2. A partir del JSON de telemetria d'una "
    "instalacio, escriu NOMES dues seccions narratives en catala, cadascuna de "
    "3 a 5 frases, amb aquest format EXACTE:\n"
    "## Resum\n<resum>\n\n## Observacions i recomanacions\n<observacions>\n\n"
    "Al Resum, descriu l'estat general de la setmana, el comportament dels tancs "
    "i si hi ha hagut alarmes. A Observacions, dona recomanacions concretes de "
    "manteniment i seguiment. Escriu de forma qualitativa i professional; NO "
    "escriguis cap xifra ni percentatge (fes servir paraules com 'baix', "
    "'elevat', 'estable', 'tres alarmes'). Respon nomes amb les dues seccions."
)

_GAS_NOM = {"N2": "nitrogen", "O2": "oxigen", "CO2": "dioxid de carboni", "Ar": "argo"}


def _num(v):
    return str(int(v)) if float(v) == int(float(v)) else ("%.1f" % float(v))


def render_header(inp):
    return "# Informe setmanal - %s (setmana %d)" % (inp["instalacio"], inp["setmana"])


def render_tanks(inp):
    lines = ["## Estat dels tancs"]
    for t in inp["tancs"]:
        delta = t["nivell_pct_final"] - t["nivell_pct_inici"]
        signe = "+" if delta >= 0 else "-"
        lines.append(
            "- **%s (%s, %s)** - nivell: %s%% -> %s%% (%s%s punts). "
            "Pressio mitjana %s bar, temperatura mitjana %s C. "
            "Consum setmanal: %s m3." % (
                t["id"], t["gas"], _GAS_NOM.get(t["gas"], t["gas"]),
                _num(t["nivell_pct_inici"]), _num(t["nivell_pct_final"]),
                signe, _num(abs(delta)), _num(t["pressio_bar_mitjana"]),
                _num(t["temp_c_mitjana"]), _num(t["consum_m3"])))
    total = sum(t["consum_m3"] for t in inp["tancs"])
    lines.append("- **Consum total de la instalacio**: %s m3." % _num(total))
    return "\n".join(lines)


def render_alarms(inp):
    lines = ["## Alarmes"]
    al = inp["alarmes"]
    if not al:
        lines.append("Sense alarmes registrades durant la setmana.")
        return "\n".join(lines)
    for a in al:
        estat = "Resolta." if a["resolta"] else "PENDENT de resolucio."
        lines.append("- **%s** al tanc %s - %s, durada %d min. %s" % (
            a["tipus"].capitalize(), a["tanc"], a["dia"], a["durada_min"], estat))
    return "\n".join(lines)


def split_narrative(text):
    """Extract (resum, observacions) from crystal output; robust to noise."""
    resum, obs = "", ""
    m_r = re.search(r"##\s*Resum\s*(.+?)(?=##|\Z)", text, re.S | re.I)
    m_o = re.search(r"##\s*Observacions[^\n]*\n(.+?)(?=##|\Z)", text, re.S | re.I)
    if m_r:
        resum = m_r.group(1).strip()
    if m_o:
        obs = m_o.group(1).strip()
    return resum, obs


def assemble(inp, resum, obs):
    return "\n\n".join([
        render_header(inp),
        "## Resum\n" + (resum or "(sense resum)"),
        render_tanks(inp),
        render_alarms(inp),
        "## Observacions i recomanacions\n" + (obs or "(sense observacions)"),
    ])
