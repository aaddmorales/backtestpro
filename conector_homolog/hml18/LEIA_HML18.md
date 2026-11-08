# BotTested Conector HOMOLOG v1.40-hml18 — ORDEM 051 (08/11/2026)

**Decisão do dono (08/11):** o cartão "Rompimento de Lateralização" segue o **fluxo padrão**. O token gerado no passo Enviar vai para o Conector. Os bots aparecem em "Meus bots" e no Monitor de Bots. A leitura em sombra roda **dentro do Conector**.

O leitor separado da O48 (pacote `O49_leitor_lateral.zip`, pasta `C:\BotTested\Lateral_O48`, chave própria, início próprio com o Windows) **deixou de ser usado**.

## O que muda em relação à hml17

| # | Mudança | Campanha |
|---|---|---|
| L1 | O campo do token aceita **dois tokens separados por espaço**: o da campanha e o `lat_…` do cartão. O campo fica mascarado. | O token da campanha segue o mesmo caminho. |
| L2 | "Meus bots" junta os bots da campanha e os do cartão. Os do cartão aparecem como `🧪 … (sombra · estado)`. | Inalterada. |
| L3 | Conectar liga também a `ponte_lateral_hml18.py`, que roda o motor da O48 sem alteração (`lateral/`, hashes iguais ao `MANIFESTO_O48`). | Inalterada. |
| L4 | A ponte confere no próprio terminal que ele é a **instalação fixada** e que a conta é **DEMO**. Se não for, recusa e não lê nada. | — |
| L5 | A trava de rede passa a liberar **2 hosts** (`homolog-homolog` e `lm-relatorio-homolog`). Produção e http continuam recusados. | Inalterada. |
| L6 | Nos bots em sombra, Reinstalar, Desinstalar e Deletar só explicam que não existe EA. Para parar, use o cartão. | — |

**Nenhuma ordem:** a ponte não chama nenhuma função de ordem. O teste `testes/test_o51_fluxo_padrao_lateral.py` confere no código e no terminal simulado (22/22).

**Limitação:** igual à hml17, o Conector HOMOLOG não abre sozinho com o Windows. A leitura em sombra só acontece com o Conector aberto e conectado.

## Instalar (PC do MT5)

1. Extraia o pacote numa pasta qualquer, por exemplo `C:\BotTested\pacote_hml18`.
2. Rode, no PowerShell dentro dessa pasta:
   `powershell -ExecutionPolicy Bypass -File .\instalar_conector_hml18.ps1`
3. O instalador:
   - confere os hashes;
   - fecha o Conector HOMOLOG;
   - guarda a hml17 em `C:\BotTested_HOMOLOG\_backup_hml17_<data>`;
   - copia a hml18;
   - remove o início automático do leitor separado, se existir;
   - reabre o Conector.
4. Na plataforma, abra o cartão e vá ao passo **4 · Enviar**. Clique em **🔑 Gerar token** e depois em **Copiar**.
5. No Conector, mantenha o token da campanha no campo, acrescente um espaço e cole o token `lat_…`. Clique em **Parar** e depois em **Conectar e monitorar**.
6. Na plataforma:
   - os bots passam a **Conectado**;
   - depois de 1 h começa a semana de coleta;
   - no Monitor de Bots aparece a seção 🧪.

**Desfazer:** feche o Conector e copie os arquivos de `_backup_hml17_<data>` de volta para `C:\BotTested_HOMOLOG`.

## Hashes (SHA-256)

Veja a lista completa em `MANIFESTO_HML18.json`, conferida pelo instalador.
