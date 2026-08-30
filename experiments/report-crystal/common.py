"""Shared prompt building for the Catalan report task."""
from __future__ import annotations
import json

INSTR = (
    "Ets un sistema de generacio d'informes de GasN2. A partir del JSON de "
    "telemetria, escriu un informe setmanal BREU en catala amb EXACTAMENT "
    "aquestes seccions:\n"
    "# Informe setmanal - <instalacio> (setmana <n>)\n"
    "## Resum\n## Estat dels tancs\n## Alarmes\n## Observacions i recomanacions\n"
    "Totes les xifres han de sortir del JSON, sense inventar-ne cap. "
    "Si no hi ha alarmes, escriu 'Sense alarmes registrades.' "
    "Respon NOMES amb l'informe en format Markdown."
)

# One exemplar (style anchor + one-shot arm). Input kept in sync with the text.
EXEMPLAR_INPUT = {
    "instalacio": "Planta Sabadell", "poblacio": "Sabadell", "setmana": 12,
    "tancs": [
        {"id": "T1", "gas": "N2", "nivell_pct_inici": 82.5, "nivell_pct_final": 47.0,
         "pressio_bar_mitjana": 8.3, "temp_c_mitjana": -182.4, "consum_m3": 640},
    ],
    "alarmes": [
        {"tipus": "nivell baix", "code": "low_level", "tanc": "T1",
         "dia": "dijous", "durada_min": 45, "resolta": True},
    ],
}

EXEMPLAR_REPORT = """# Informe setmanal - Planta Sabadell (setmana 12)

## Resum
Setmana amb funcionament general correcte a la instalacio de Sabadell. El tanc T1 ha registrat un consum notable i una alarma de nivell baix que va quedar resolta.

## Estat dels tancs
- T1 (N2): nivell del 82.5% al 47.0%, pressio mitjana 8.3 bar, temperatura mitjana -182.4 C, consum 640 m3.

## Alarmes
- Alarma de nivell baix al tanc T1 (dijous, 45 min). Resolta.

## Observacions i recomanacions
El descens de nivell del T1 es coherent amb el consum registrat. Es recomana programar el proper subministrament abans que el nivell baixi del 30% per evitar noves alarmes de nivell baix."""


def build_messages(inp, shots=0):
    msgs = [{"role": "system", "content": INSTR}]
    if shots:
        msgs.append({"role": "user",
                     "content": json.dumps(EXEMPLAR_INPUT, ensure_ascii=False)})
        msgs.append({"role": "assistant", "content": EXEMPLAR_REPORT})
    msgs.append({"role": "user", "content": json.dumps(inp, ensure_ascii=False)})
    return msgs
