"""Synthetic HTML instruction dataset generator.
Produces complete, valid, self-contained HTML5 documents paired with natural-language
instructions. Fully offline / templated. Output: html_data.jsonl  (one {instruction, html} per line)
"""
import random, json

R = random.Random(42)

# curated palettes: (bg, surface, text, muted, accent, accent2)
PALETTES = [
    ("#0f172a", "#1e293b", "#f1f5f9", "#94a3b8", "#38bdf8", "#818cf8"),  # slate/blue dark
    ("#fffaf0", "#fff", "#2b2320", "#6b5d54", "#c0693b", "#e0a458"),      # warm cream
    ("#ffffff", "#f7f7f9", "#111827", "#6b7280", "#4f46e5", "#ec4899"),   # clean indigo/pink
    ("#f0fdf4", "#fff", "#14532d", "#4d7c5a", "#16a34a", "#0891b2"),      # green/teal
    ("#1a1a2e", "#16213e", "#e6e6e6", "#a0a0b0", "#e94560", "#0f3460"),   # night red
    ("#fdf4ff", "#fff", "#3b0764", "#7c5295", "#a21caf", "#f59e0b"),      # purple/amber
    ("#ffffff", "#fafafa", "#18181b", "#71717a", "#f97316", "#0ea5e9"),   # orange/sky
    ("#f8fafc", "#fff", "#0f172a", "#64748b", "#0d9488", "#7c3aed"),      # teal/violet
]
FONTS = [
    "system-ui, -apple-system, sans-serif",
    "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    "Georgia, 'Times New Roman', serif",
    "'Inter', system-ui, sans-serif",
]

BRANDS = ["Bean There","Lumen","Northwind","Vela","Pixel Forge","Everbloom","Cascade","Nimbus",
    "Foundry","Aria","Meridian","Slate & Co","Wanderlust","BrightPath","Kettle","Studio Oak",
    "Verdant","Tandem","Halcyon","Ridgeline","Ember","Quill","Harbor","Solstice"]
TAGLINES = ["Do more with less.","Built for teams that ship.","Your work, beautifully organized.",
    "Crafted for the modern web.","Simple tools, powerful results.","Where ideas take shape.",
    "The fast way to get started.","Designed to feel effortless.","Everything you need, nothing you don't.",
    "Make something people love."]
FEATURES = [
    ("Lightning fast","Loads in milliseconds so nobody waits around."),
    ("Secure by default","End-to-end encryption keeps your data yours."),
    ("Works everywhere","Responsive layouts for phone, tablet and desktop."),
    ("Easy to use","An interface your whole team understands on day one."),
    ("Always in sync","Changes appear instantly across every device."),
    ("Built to scale","From your first user to your millionth."),
    ("Thoughtful support","Real humans, ready when you need them."),
    ("Open and flexible","Integrates with the tools you already love."),
]
CATEGORIES = ["coffee subscription","project management app","design studio","photography portfolio",
    "SaaS analytics tool","fitness app","online bookstore","travel agency","fintech startup",
    "meal-kit service","music streaming service","developer tool","interior design firm","yoga studio"]

def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def base_css(p, font):
    bg, surf, text, muted, acc, acc2 = p
    return f"""*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:{font};background:{bg};color:{text};line-height:1.6}}
a{{color:{acc};text-decoration:none}}
.wrap{{max-width:1100px;margin:0 auto;padding:0 1.5rem}}
.btn{{display:inline-block;padding:.8rem 1.6rem;border-radius:8px;font-weight:600;background:{acc};color:#fff}}
.btn.alt{{background:transparent;border:1px solid {acc}}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:1.2rem 1.5rem;max-width:1100px;margin:0 auto}}
nav .links a{{margin-left:1.5rem;color:{muted}}}
footer{{background:{surf};color:{muted};text-align:center;padding:2.5rem 1rem;margin-top:4rem}}
h1{{font-size:2.8rem;line-height:1.15;margin-bottom:1rem}}
h2{{font-size:2rem;margin-bottom:1.5rem}}
section{{padding:4rem 0}}"""

def nav(brand, acc):
    return (f'<nav><strong style="font-size:1.2rem">{esc(brand)}</strong>'
            f'<div class="links"><a href="#">Features</a><a href="#">Pricing</a>'
            f'<a href="#">About</a><a class="btn" href="#">Sign up</a></div></nav>')

def footer(brand):
    return f'<footer><div class="wrap">&copy; 2026 {esc(brand)}. All rights reserved.</div></footer>'

def doc(title, css, body):
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>{esc(title)}</title>\n<style>\n{css}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>')

# ---- page builders: each returns (instruction, html) ----
def landing():
    p, font = R.choice(PALETTES), R.choice(FONTS)
    brand, cat = R.choice(BRANDS), R.choice(CATEGORIES)
    tag = R.choice(TAGLINES); acc = p[4]
    feats = R.sample(FEATURES, 3)
    cards = "".join(
        f'<div class="card"><h3>{esc(t)}</h3><p style="color:{p[3]}">{esc(d)}</p></div>' for t,d in feats)
    css = base_css(p, font) + f"""
.hero{{text-align:center;padding:6rem 0}}
.hero p.sub{{font-size:1.25rem;color:{p[3]};max-width:46ch;margin:0 auto 2rem}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1.5rem}}
.card{{background:{p[1]};padding:2rem;border-radius:12px}}
.card h3{{margin-bottom:.5rem;color:{p[4]}}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}.hero h1{{font-size:2rem}}}}"""
    body = (nav(brand, acc) +
        f'<section class="hero"><div class="wrap"><h1>{esc(brand)}</h1>'
        f'<p class="sub">{esc(tag)} The {esc(cat)} built to feel effortless.</p>'
        f'<a class="btn" href="#">Get started</a> <a class="btn alt" href="#">Learn more</a></div></section>'
        f'<section><div class="wrap"><h2>Why {esc(brand)}?</h2><div class="grid">{cards}</div></div></section>'
        + footer(brand))
    instr = R.choice([
        f"Create a modern landing page for a {cat} called '{brand}' with a hero, three feature cards, and a footer.",
        f"Build a complete landing page for '{brand}', a {cat}. Include a nav bar, hero section, 3 features, and footer.",
        f"Design a single-page website for a {cat} startup named '{brand}'.",
    ])
    return instr, doc(brand, css, body)

def pricing():
    p, font = R.choice(PALETTES), R.choice(FONTS)
    brand = R.choice(BRANDS); acc = p[4]
    tiers = [("Free","$0",["1 project","Community support","1 GB storage"]),
             ("Pro","$19",["Unlimited projects","Priority support","50 GB storage","Advanced analytics"]),
             ("Enterprise","$99",["Everything in Pro","SSO & audit logs","Dedicated manager","Unlimited storage"])]
    def tier(name, price, feats, hot):
        li = "".join(f'<li>{esc(f)}</li>' for f in feats)
        return (f'<div class="tier{" hot" if hot else ""}">'
                f'<h3>{esc(name)}</h3><div class="price">{esc(price)}<span>/mo</span></div>'
                f'<ul>{li}</ul><a class="btn" href="#">Choose {esc(name)}</a></div>')
    cards = "".join(tier(n,pr,f,i==1) for i,(n,pr,f) in enumerate(tiers))
    css = base_css(p, font) + f"""
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1.5rem;align-items:start}}
.tier{{background:{p[1]};padding:2rem;border-radius:14px;text-align:center;border:1px solid {p[1]}}}
.tier.hot{{border-color:{p[4]};transform:scale(1.05)}}
.price{{font-size:2.5rem;font-weight:800;margin:1rem 0;color:{p[4]}}}
.price span{{font-size:1rem;color:{p[3]};font-weight:400}}
.tier ul{{list-style:none;margin:1.5rem 0;text-align:left}}
.tier li{{padding:.4rem 0;color:{p[3]}}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}"""
    body = (nav(brand, acc) +
        f'<section><div class="wrap" style="text-align:center"><h2>Simple, transparent pricing</h2>'
        f'<p style="color:{p[3]};margin-bottom:3rem">Pick the plan that fits your team.</p>'
        f'<div class="grid">{cards}</div></div></section>' + footer(brand))
    instr = R.choice([
        f"Create a pricing page for '{brand}' with three tiers (Free, Pro, Enterprise) as side-by-side cards, the middle one highlighted.",
        f"Build a three-tier pricing table for '{brand}'. Highlight the recommended Pro plan.",
        f"Design a clean pricing page with Free, Pro and Enterprise columns for '{brand}'.",
    ])
    return instr, doc(f"Pricing - {brand}", css, body)

def portfolio():
    p, font = R.choice(PALETTES), R.choice(FONTS)
    name = R.choice(["Jordan Reyes","Sam Okafor","Alex Lindqvist","Mika Tanaka","Rowan Bell"])
    craft = R.choice(["Photographer","Product Designer","Illustrator","Architect","Filmmaker"])
    acc = p[4]
    tiles = "".join(
        f'<div class="tile" style="background:linear-gradient(135deg,{p[4]},{p[5]})"><span>Project {i+1}</span></div>'
        for i in range(6))
    css = base_css(p, font) + f"""
.hero{{padding:7rem 0 3rem}}
.hero h1{{font-size:3.4rem}}.hero p{{color:{p[3]};font-size:1.2rem}}
.gallery{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}}
.tile{{aspect-ratio:4/3;border-radius:12px;display:flex;align-items:flex-end;padding:1rem;color:#fff;font-weight:600}}
@media(max-width:800px){{.gallery{{grid-template-columns:1fr 1fr}}.hero h1{{font-size:2.2rem}}}}"""
    body = (nav(name, acc) +
        f'<section class="hero"><div class="wrap"><h1>{esc(name)}</h1>'
        f'<p>{esc(craft)} crafting work that lingers. Selected projects below.</p></div></section>'
        f'<section style="padding-top:0"><div class="wrap"><div class="gallery">{tiles}</div></div></section>'
        + footer(name))
    instr = R.choice([
        f"Create a portfolio site for {name}, a {craft.lower()}, with a hero and a 6-item project gallery grid.",
        f"Build a striking portfolio hero and gallery for {craft.lower()} {name}.",
        f"Design a single-page portfolio for {name} showing a hero section and a grid of work.",
    ])
    return instr, doc(name, css, body)

def cta_signup():
    p, font = R.choice(PALETTES), R.choice(FONTS)
    brand = R.choice(BRANDS); acc = p[4]
    css = base_css(p, font) + f"""
.hero{{min-height:70vh;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;
background:linear-gradient(135deg,{p[4]},{p[5]});color:#fff;padding:2rem}}
.hero h1{{font-size:3rem;max-width:18ch}}.hero p{{font-size:1.25rem;max-width:44ch;opacity:.92;margin:1rem 0 2rem}}
form{{display:flex;gap:.5rem;flex-wrap:wrap;justify-content:center}}
input{{padding:.9rem 1rem;border:none;border-radius:8px;min-width:260px;font-size:1rem}}
.hero .btn{{background:#fff;color:{p[4]}}}"""
    tag = R.choice(TAGLINES)
    body = (f'<section class="hero"><h1>{esc(brand)}</h1><p>{esc(tag)}</p>'
            f'<form><input type="email" placeholder="you@example.com" aria-label="Email">'
            f'<button class="btn" type="submit">Join the waitlist</button></form></section>' + footer(brand))
    instr = R.choice([
        f"Create a bold full-screen waitlist signup page for '{brand}' with an email input and a gradient background.",
        f"Build a centered hero call-to-action page for '{brand}' with an email capture form.",
    ])
    return instr, doc(brand, css, body)

def about():
    p, font = R.choice(PALETTES), R.choice(FONTS)
    brand = R.choice(BRANDS); acc = p[4]
    stats = [("2018","Founded"),("40+","Team members"),("120k","Happy users"),("30","Countries")]
    sc = "".join(f'<div class="stat"><div class="n">{esc(n)}</div><div style="color:{p[3]}">{esc(l)}</div></div>' for n,l in stats)
    css = base_css(p, font) + f"""
.hero{{padding:6rem 0 2rem;text-align:center}}
.hero p{{color:{p[3]};max-width:52ch;margin:0 auto;font-size:1.15rem}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;text-align:center}}
.stat{{background:{p[1]};padding:2rem 1rem;border-radius:12px}}
.stat .n{{font-size:2.2rem;font-weight:800;color:{p[4]}}}
@media(max-width:700px){{.stats{{grid-template-columns:1fr 1fr}}}}"""
    body = (nav(brand, acc) +
        f'<section class="hero"><div class="wrap"><h1>About {esc(brand)}</h1>'
        f'<p>We started {esc(brand)} to make everyday work feel a little more human. '
        f'Today we help teams around the world do their best work.</p></div></section>'
        f'<section style="padding-top:0"><div class="wrap"><div class="stats">{sc}</div></div></section>'
        + footer(brand))
    instr = R.choice([
        f"Create an About page for '{brand}' with a mission statement and a row of company stats.",
        f"Build an about-us page for '{brand}' including a short story and 4 key metrics.",
    ])
    return instr, doc(f"About {brand}", css, body)

BUILDERS = [landing, pricing, portfolio, cta_signup, about]
WEIGHTS  = [3, 2, 2, 1, 1]

def main(n=420, path="html_data.jsonl"):
    rows, seen = [], set()
    while len(rows) < n:
        b = R.choices(BUILDERS, weights=WEIGHTS)[0]
        instr, html = b()
        key = (instr, html[:60])
        if key in seen: continue
        seen.add(key)
        rows.append({"instruction": instr, "html": html})
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    lens = [len(r["html"]) for r in rows]
    print(f"wrote {len(rows)} examples -> {path}")
    print(f"html chars: min={min(lens)} max={max(lens)} mean={sum(lens)//len(lens)}")
    by = {}
    for r in rows:
        k = r["instruction"].split("'")[0][:20]
        by[k] = by.get(k,0)+1
    print("type mix:", by)

if __name__ == "__main__":
    main()
