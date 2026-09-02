"""Rich state features for the learned relevance model Q(state, form) -> P(form helps).
Pure-Python (no numpy/sklearn). The upgrade over the coarse k-NN signature is BELIEF SHAPE
(suspiciousness entropy) + suspicious-site AST + fix-depth-correlated structure."""
import ast, math

FORMS = ["ENUMERATE(0)", "ENUMERATE(1)", "ENUMERATE(2)", "INTERPOLATE", "RESET"]
_NODE_KINDS = ["Compare", "BinOp", "BoolOp", "Call", "ListComp", "Subscript", "Return",
               "Constant", "Name", "Assign", "If", "For", "While"]

def _entropy(vals):
    s = sum(vals)
    if s <= 0: return 0.0
    ps = [v / s for v in vals if v > 0]
    return -sum(p * math.log(p + 1e-12) for p in ps)

def baseline_error(state):
    """Error class of the pristine buggy program on its first failing test."""
    import reasoner_code as rc
    try: code = compile(ast.fix_missing_locations(state.orig), "<c>", "exec")
    except Exception: return "syntax"
    ns = {}
    try: exec(code, ns)
    except Exception: return "syntax"
    fn = ns.get(state.name)
    if not callable(fn): return "nofunc"
    import copy, types
    for inp, exp in state.all_tests:
        try:
            r = fn(*copy.deepcopy(inp))
            if isinstance(r, types.GeneratorType): r = list(r)
            if r != exp: return "wrong"
        except RecursionError: return "recursion"
        except (IndexError, KeyError): return "index"
        except NameError: return "name"
        except TypeError: return "type"
        except ZeroDivisionError: return "zerodiv"
        except Exception: return "other"
    return "none"

_ERR_CLASSES = ["wrong", "recursion", "index", "name", "type", "zerodiv", "other", "syntax", "nofunc", "none"]

def structural(tree, fname):
    recursive = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == fname
                    for n in ast.walk(tree))
    has_comp = any(isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
                   for n in ast.walk(tree))
    has_loop = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
    size = sum(1 for _ in ast.walk(tree))
    return recursive, has_comp, has_loop, size

def top_susp_kinds(tree, susp):
    top = max(susp.items(), key=lambda kv: kv[1])[0] if susp else None
    kinds = {k: 0 for k in _NODE_KINDS}
    depth = 0
    if top is not None:
        for node in ast.walk(tree):
            if getattr(node, "lineno", None) == top:
                nm = type(node).__name__
                if nm in kinds: kinds[nm] += 1
    return kinds

def feature_row(state, form_name, tried=(), err_cache=None):
    """Fixed-order float vector for (state, candidate form)."""
    susp = state.susp or {}
    svals = [v for v in susp.values() if v > 0]
    ent = _entropy(svals); mx = max(svals) if svals else 0.0; nsusp = len(svals)
    fname = state.name
    rec, comp, loop, size = structural(state.orig, fname)
    kinds = top_susp_kinds(state.tree, susp)
    ntot = len(state.all_tests) or 1
    exp0 = state.all_tests[0][1] if state.all_tests else None
    out_is_list = 1.0 if isinstance(exp0, (list, tuple)) else 0.0
    out_is_bool = 1.0 if isinstance(exp0, bool) else 0.0
    err = err_cache if err_cache is not None else baseline_error(state)
    row = [ent, mx, float(nsusp), float(state.best), state.best / ntot, float(ntot), float(size),
           float(rec), float(comp), float(loop), out_is_list, out_is_bool,
           float(len(tried)), float(getattr(state, "stratum_seen", 0))]
    row += [float(kinds[k]) for k in _NODE_KINDS]
    row += [1.0 if err == e else 0.0 for e in _ERR_CLASSES]
    row += [1.0 if form_name == f else 0.0 for f in FORMS]
    row += [1.0 if f in tried else 0.0 for f in FORMS]   # which forms already tried this episode
    return row

def feature_names():
    base = ["susp_entropy", "susp_max", "n_susp", "best_nfail", "frac_fail", "n_tests", "ast_size",
            "recursive", "has_comp", "has_loop", "out_is_list", "out_is_bool", "n_tried", "stratum_seen"]
    return (base + [f"node_{k}" for k in _NODE_KINDS] + [f"err_{e}" for e in _ERR_CLASSES]
            + [f"form_{f}" for f in FORMS] + [f"tried_{f}" for f in FORMS])
