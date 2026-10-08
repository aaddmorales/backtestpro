"""Bancada: o relato `cortes` que o leitor 1.7 grava (contrato corte-ciclo-2), para os testes da API."""
OR = [{"identificado_em": ["M5:rompe_fundo"], "decidido_por": ["M15:fecha_abaixo_canal"]}]


def cortes(agora_compra=False, agora_venda=False, fech_compra=False, fech_venda=False, contrato="corte-ciclo-2", origem=None):
    def lado(c):
        return {"corta": bool(c), "origem": (origem if origem is not None else OR) if c else [],
                "integracao_anterior": {"corta": bool(c), "motivo": "", "andares_que_decidiram": ["M15"] if c else []}, "divergencia": None}
    return {"contrato": contrato, "regra": "teste", "andares_do_contrato": ["M1", "M5", "M10", "M15"],
            "nao_cortam": ["M30", "H1", "H4", "D1", "W1", "MN1"],
            "barras": {"que_abre_agora": {"compra": lado(agora_compra), "venda": lado(agora_venda)},
                       "ultima_fechada": {"compra": lado(fech_compra), "venda": lado(fech_venda)}}}
