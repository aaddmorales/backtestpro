"""Supabase FALSO em memória para os testes da O48 (só as operações usadas por lateral_o48)."""
import copy, itertools


class _Q:
    def __init__(self, db, tab): self.db, self.tab, self.op, self.filt, self.dados, self.ordem, self.rng, self.conf = db, tab, "select", [], None, None, None, {}
    def select(self, *_a, **_k): self.op = "select"; return self
    def eq(self, k, v): self.filt.append((k, v)); return self
    def order(self, k, desc=False): self.ordem = (k, desc); return self
    def range(self, a, b): self.rng = (a, b); return self
    def limit(self, n): self.rng = (0, n - 1); return self
    def insert(self, d): self.op, self.dados = "insert", d; return self
    def update(self, d): self.op, self.dados = "update", d; return self
    def upsert(self, d, on_conflict=None, ignore_duplicates=False): self.op, self.dados, self.conf = "upsert", d, {"on": on_conflict, "ign": ignore_duplicates}; return self
    def _ok(self, r): return all(str(r.get(k)) == str(v) for k, v in self.filt)
    def execute(self):
        T = self.db.t.setdefault(self.tab, []); out = []
        if self.op == "select":
            out = [copy.deepcopy(r) for r in T if self._ok(r)]
            if self.ordem: out.sort(key=lambda r: (r.get(self.ordem[0]) is None, r.get(self.ordem[0])), reverse=self.ordem[1])
            if self.rng: out = out[self.rng[0]:self.rng[1] + 1]
        elif self.op == "insert":
            for d in (self.dados if isinstance(self.dados, list) else [self.dados]):
                if self.tab == "lateral_bots" and d.get("estado", "criado") != "parado" and any(r["user_id"] == d["user_id"] and r["ativo"] == d["ativo"] and r["tf"] == d["tf"] and r["estado"] != "parado" for r in T):
                    raise RuntimeError("unique violation lateral_bots_ativo_uk")
                r = {"id": next(self.db.ids), "estado": "criado", "confirmacao": {}, "coleta_inicio": None, "coleta_fim": None, "criado_em": "2026-01-01T00:00:00+00:00", **d}; T.append(r); out.append(copy.deepcopy(r))
        elif self.op == "update":
            for r in T:
                if self._ok(r): r.update(copy.deepcopy(self.dados)); out.append(copy.deepcopy(r))
        elif self.op == "upsert":
            keys = (self.conf["on"] or "id").split(",")
            for d in (self.dados if isinstance(self.dados, list) else [self.dados]):
                ex = next((r for r in T if all(str(r.get(k)) == str(d.get(k)) for k in keys)), None)
                if ex is None: r = {"id": next(self.db.ids), **copy.deepcopy(d)}; T.append(r); out.append(r)
                elif not self.conf["ign"]: ex.update(copy.deepcopy(d)); out.append(ex)
        return type("R", (), {"data": out})()


class FakeSB:
    def __init__(self): self.t = {}; self.ids = itertools.count(1)
    def table(self, n): return _Q(self, n)
