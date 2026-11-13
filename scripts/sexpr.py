"""Minimal KiCad S-expression reader/writer and symbol-library lookup."""
import re
from pathlib import Path

KICAD = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
ROOT = Path(__file__).resolve().parent.parent
LIBDIRS = {"fc": ROOT / "hw/lib/fc.kicad_sym"}

_TOK = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)')


class Sym(str):
    """Bare (unquoted) atom."""


def parse(text):
    stack, cur = [], []
    for m in _TOK.finditer(text):
        t = m.group(1)
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        elif t.startswith('"'):
            cur.append(t[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            cur.append(Sym(t))
    return cur[0]


def dump(x, ind=0):
    if isinstance(x, list):
        inner = [dump(e, ind + 1) for e in x]
        flat = "(" + " ".join(inner) + ")"
        if len(flat) < 100 and "\n" not in flat:
            return flat
        return "(" + inner[0] + "".join("\n" + "\t" * (ind + 1) + s for s in inner[1:]) + ")"
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, (int, float)):
        return f"{x:.4f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)
    return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def first(node, key):
    r = find(node, key)
    return r[0] if r else None


_libcache = {}


def load_lib(lib):
    if lib not in _libcache:
        path = LIBDIRS.get(lib, KICAD / "symbols" / f"{lib}.kicad_sym")
        _libcache[lib] = {s[1]: s for s in find(parse(path.read_text()), "symbol")}
    return _libcache[lib]


def get_symbol(lib_id):
    """Return a flattened symbol definition named 'lib:name' (resolves 'extends')."""
    lib, name = lib_id.split(":")
    syms = load_lib(lib)
    sym = syms[name]
    ext = first(sym, "extends")
    if ext:
        parent = syms[ext[1]]
        props = {p[1]: p for p in find(sym, "property")}
        out = [Sym("symbol"), lib_id]
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property":
                out.append(props.pop(c[1], c))
            elif isinstance(c, list) and c[0] == "symbol":
                out.append([Sym("symbol"), c[1].replace(ext[1], name, 1)] + c[2:])
            else:
                out.append(c)
        out[3:3] = list(props.values())
        return out
    return [Sym("symbol"), lib_id] + sym[2:]


def pins(symdef):
    """{number: (name, x, y, angle, type)} for unit 1 / common units."""
    out = {}
    for sub in find(symdef, "symbol"):
        unit = sub[1].rsplit("_", 2)[-2]
        if unit not in ("0", "1"):
            continue
        for p in find(sub, "pin"):
            at = first(p, "at")
            num = first(p, "number")[1]
            name = first(p, "name")[1]
            out[num] = (name, float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, str(p[1]))
    return out
