"""Synthetic Pyodide-idiom dataset: instruction -> CORRECT Pyodide Python.
Tests whether API KNOWLEDGE (unlike structural validity) installs at rank-1.
Output: pyodide_data.jsonl  {instruction, code}
"""
import random, json
R = random.Random(7)
IDS=["output","result","status","title","msg","label","content","box","panel","note"]
TXT=["Hello","Done","Loading...","Welcome","Ready","Success","Updated","Click me","Saved","Error"]
INP=["name","email","search","query","username","city","code","amount"]
PKG=["requests","numpy","pandas","beautifulsoup4","pyyaml","pillow","scipy"]
URL=["https://api.example.com/data.json","https://example.com/users.json","/api/items","https://data.org/feed.json"]
COL=["red","#2563eb","teal","rgb(20,20,20)","goldenrod","#16a34a"]
CLS=["active","hidden","selected","highlight","open","done"]
EVT=["click","mouseover","change","input"]
TAG=["div","p","span","li","button"]

def set_text():
    i=R.choice(IDS); t=R.choice(TXT)
    code=(f'from js import document\n\n'
          f'document.getElementById("{i}").textContent = "{t}"')
    ins=R.choice([f'Using Pyodide in the browser, set the text of the element with id "{i}" to "{t}".',
                  f'With Pyodide, update the HTML element "{i}" so it displays "{t}".'])
    return ins, code

def read_input():
    i=R.choice(INP)
    code=(f'from js import document\n\n'
          f'value = document.getElementById("{i}").value\n'
          f'print(value)')
    ins=R.choice([f'Using Pyodide, read the current value of the input element with id "{i}".',
                  f'With Pyodide, get the text a user typed into the "{i}" input.'])
    return ins, code

def click_listener():
    i=R.choice(IDS); ev=R.choice(EVT); t=R.choice(TXT)
    code=(f'from js import document\n'
          f'from pyodide.ffi import create_proxy\n\n'
          f'def handler(event):\n    print("{t}")\n\n'
          f'proxy = create_proxy(handler)\n'
          f'document.getElementById("{i}").addEventListener("{ev}", proxy)')
    ins=R.choice([f'Using Pyodide, add a {ev} event listener to the element with id "{i}" that prints "{t}".',
                  f'With Pyodide, run a handler printing "{t}" when the "{i}" element fires "{ev}".'])
    return ins, code

def micropip_install():
    p=R.choice(PKG)
    code=(f'import micropip\n\n'
          f'await micropip.install("{p}")\n'
          f'import {p.split("4")[0].replace("beautifulsoup","bs4").replace("pillow","PIL").replace("pyyaml","yaml")}')
    ins=R.choice([f'Using Pyodide, install the "{p}" package at runtime from Python.',
                  f'With Pyodide, add the "{p}" dependency inside the browser session.'])
    return ins, code

def pyfetch_json():
    u=R.choice(URL)
    code=(f'from pyodide.http import pyfetch\n\n'
          f'response = await pyfetch("{u}")\n'
          f'data = await response.json()\n'
          f'print(data)')
    ins=R.choice([f'Using Pyodide, fetch JSON asynchronously from {u}.',
                  f'With Pyodide, load and parse JSON from {u} without blocking.'])
    return ins, code

def create_append():
    tag=R.choice(TAG); t=R.choice(TXT); i=R.choice(IDS)
    code=(f'from js import document\n\n'
          f'el = document.createElement("{tag}")\n'
          f'el.textContent = "{t}"\n'
          f'document.getElementById("{i}").appendChild(el)')
    ins=R.choice([f'Using Pyodide, create a <{tag}> element containing "{t}" and append it to the element with id "{i}".',
                  f'With Pyodide, add a new {tag} saying "{t}" inside "{i}".'])
    return ins, code

def set_style():
    i=R.choice(IDS); c=R.choice(COL)
    prop=R.choice([("color",c),("backgroundColor",c),("display","none"),("fontWeight","bold")])
    code=(f'from js import document\n\n'
          f'document.getElementById("{i}").style.{prop[0]} = "{prop[1]}"')
    ins=R.choice([f'Using Pyodide, set the {prop[0]} style of the "{i}" element to "{prop[1]}".',
                  f'With Pyodide, restyle "{i}" so its {prop[0]} is "{prop[1]}".'])
    return ins, code

def toggle_class():
    i=R.choice(IDS); c=R.choice(CLS); op=R.choice(["add","remove","toggle"])
    code=(f'from js import document\n\n'
          f'document.getElementById("{i}").classList.{op}("{c}")')
    ins=R.choice([f'Using Pyodide, {op} the CSS class "{c}" on the element with id "{i}".',
                  f'With Pyodide, {op} the "{c}" class of "{i}".'])
    return ins, code

BUILDERS=[set_text,read_input,click_listener,micropip_install,pyfetch_json,create_append,set_style,toggle_class]

def main(n=280, path="pyodide_data.jsonl"):
    rows, seen=[], set()
    while len(rows)<n:
        ins,code=R.choice(BUILDERS)()
        k=(ins,code)
        if k in seen: continue
        seen.add(k); rows.append({"instruction":ins,"code":code})
    with open(path,"w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r)+"\n")
    print(f"wrote {len(rows)} -> {path}")
    by={}
    for r in rows:
        k=r["code"].split("\n")[0][:24]; by[k]=by.get(k,0)+1
    print("first-line mix:", by)
    print("sample:\n", rows[0]["instruction"], "\n---\n", rows[0]["code"])

if __name__=="__main__": main()
