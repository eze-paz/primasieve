"""Track B: reasoning with BELIEFS AS INPUTS (imperfect information). Kuhn poker + CFR.

The perfect-info search (azlite/bugfix) assumes the state is fully observed. Belief-state
reasoning is what you need when the decisive variable is HIDDEN. Kuhn poker is the minimal
such game: you know your card, not the opponent's -> you must act on a BELIEF over their card.

CFR (counterfactual regret) is the canonical belief reasoner: the policy is a function of the
INFORMATION SET (your card + public history), which encodes the belief over the hidden card.
Verifiable target (the analog of our test-reward): converges to Nash -> game value = -1/18 for
player 1, exploitability -> 0. Then we show (a) the explicit posterior belief driving a decision,
and (b) a belief-BLIND agent is far more exploitable and gets robbed by the belief agent.

ReBeL = this (CFR) + depth-limited search + a value net over the public belief state; Deep CFR =
neural CFR for games too big to tabulate. Kuhn is the exact-solvable base rung.
"""
import random
from itertools import permutations, product
random.seed(0)
# cards 0,1,2 = J,Q,K. actions: 0='p'(pass/check/fold), 1='b'(bet/call). history over {'p','b'}.

class Node:
    def __init__(s): s.regret=[0.0,0.0]; s.strat_sum=[0.0,0.0]
    def strategy(s, w):
        r=[max(x,0) for x in s.regret]; n=sum(r)
        st=[x/n for x in r] if n>0 else [0.5,0.5]
        for a in range(2): s.strat_sum[a]+=w*st[a]
        return st
    def avg(s):
        n=sum(s.strat_sum)
        return [x/n for x in s.strat_sum] if n>0 else [0.5,0.5]

nodes={}

def cfr(cards, history, p0, p1):
    plays=len(history); player=plays%2; opp=1-player
    if plays>1:                                   # terminal payoff to CURRENT player
        tp=history[-1]=='p'; db=history[-2:]=='bb'; higher=cards[player]>cards[opp]
        if tp:
            if history=='pp': return 1 if higher else -1
            return 1                              # opponent folded to a bet
        if db:
            return 2 if higher else -2
    info=str(cards[player])+history
    node=nodes.setdefault(info, Node())
    st=node.strategy(p0 if player==0 else p1)
    util=[0.0,0.0]; nu=0.0
    for a in range(2):
        nh=history+('p' if a==0 else 'b')
        util[a]= -cfr(cards, nh, p0*st[a], p1) if player==0 else -cfr(cards, nh, p0, p1*st[a])
        nu+=st[a]*util[a]
    cf = p1 if player==0 else p0
    for a in range(2): node.regret[a]+= cf*(util[a]-nu)
    return nu

def train(iters):
    deck=[0,1,2]; total=0.0
    for _ in range(iters):
        random.shuffle(deck)
        total+=cfr(deck[:2], "", 1, 1)
    return total/iters

# ---------- exact evaluation & exploitability via brute-force best response ----------
def p0_payoff(history, cards):
    h=history
    if h=='pp': return 1 if cards[0]>cards[1] else -1
    if h=='bp': return 1
    if h=='pbp': return -1
    if h in ('bb','pbb'): return 2 if cards[0]>cards[1] else -2
    return None

def node_val(cards, history, s0, s1):
    t=p0_payoff(history, cards)
    if t is not None: return t
    plays=len(history); player=plays%2
    info=str(cards[player])+history
    st=(s0 if player==0 else s1)[info]
    v=0.0
    for a in range(2):
        v+= st[a]*node_val(cards, history+('p' if a==0 else 'b'), s0, s1)
    return v

def game_value(s0, s1):
    return sum(node_val(list(c), "", s0, s1) for c in permutations([0,1,2],2))/6.0

def infosets(player):
    hs=['','pb'] if player==0 else ['p','b']
    return [str(c)+h for c in (0,1,2) for h in hs]

def best_response_value(fixed, fixed_is_p1):
    """max value the responder (the other player) can get, in responder's own utils."""
    resp_p = 0 if fixed_is_p1 else 1
    keys=infosets(resp_p)
    best=None
    for combo in product([0,1],repeat=len(keys)):
        pure={k:([1,0] if a==0 else [0,1]) for k,a in zip(keys,combo)}
        s0,s1=(pure,fixed) if resp_p==0 else (fixed,pure)
        gv=game_value(s0,s1)                       # payoff to p0
        val = gv if resp_p==0 else -gv             # responder's own payoff
        if best is None or val>best: best=val
    return best

def avg_strategy(player):
    return {k: nodes[k].avg() for k in infosets(player) if k in nodes}

if __name__=="__main__":
    import time; t0=time.time()
    gv_train=train(200000)
    s0=avg_strategy(0); s1=avg_strategy(1)
    # fill any unvisited infoset (shouldn't happen) with uniform
    for p in (0,1):
        for k in infosets(p): (s0 if p==0 else s1).setdefault(k,[0.5,0.5])
    gv=game_value(s0,s1)
    br0=best_response_value(s1, fixed_is_p1=True)    # p0 best-responds to avg p1
    br1=best_response_value(s0, fixed_is_p1=False)   # p1 best-responds to avg p0
    nashconv=br0+br1
    print(f"CFR on Kuhn poker, 200k iters, {time.time()-t0:.1f}s")
    print(f"  game value (P0)   = {gv:+.4f}   (Nash target -1/18 = {-1/18:+.4f})")
    print(f"  exploitability    = {nashconv/2:.5f}  (NashConv {nashconv:.5f} -> 0 at Nash)")
    print(f"  P0 best-resp val  = {br0:+.4f} | P1 best-resp val = {br1:+.4f}")

    print("\nBELIEF as input (posterior over opponent's hidden card):")
    # P1 facing a BET, holding Q(=1): belief over P0's card given P0 bet (avg strategy)
    #   prior 1/2 each of {J=0,K=2}; posterior ∝ P0's bet-prob with that card
    for mycard,label in [(1,'Q'),(0,'J')]:
        others=[c for c in (0,1,2) if c!=mycard]
        w={c: 0.5*s0[str(c)][1] for c in others}          # P0 bet from ''  (action index1=bet)
        Z=sum(w.values()) or 1e-9
        post={c: w[c]/Z for c in others}
        act=s1[str(mycard)+'b']
        nm={0:'J',1:'Q',2:'K'}
        print(f"  P1 holds {label}, sees P0 bet -> belief P0 has "
              f"{ {nm[c]:round(post[c],2) for c in others} }; P1 calls w.p. {act[1]:.2f}")

    print("\nBELIEF-AWARE vs BELIEF-BLIND (blind = ignores card+history, plays 50/50 everywhere):")
    blind={k:[0.5,0.5] for k in infosets(0)+infosets(1)}
    b0={k:blind[k] for k in infosets(0)}; b1={k:blind[k] for k in infosets(1)}
    expl_blind = (best_response_value(b1,True)+best_response_value(b0,False))/2
    ev_cfr_vs_blind = game_value(s0, b1)             # CFR as P0 robbing blind P1 (P0 utils)
    ev_blind_vs_cfr = game_value(b0, s1)             # blind P0 vs CFR P1
    print(f"  exploitability: CFR {nashconv/2:.4f}  vs  blind {expl_blind:.4f}")
    print(f"  head-to-head EV(P0): CFR-vs-blind {ev_cfr_vs_blind:+.4f} (>Nash {gv:+.4f} => CFR exploits blind)")
    print(f"                       blind-vs-CFR {ev_blind_vs_cfr:+.4f} (blind bleeds as P0 too)")
    print("\n=> belief-conditioned policy is ~unexploitable AND extracts value from a belief-blind one.")
