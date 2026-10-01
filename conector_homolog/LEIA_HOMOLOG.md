# BotTested Conector HOMOLOG — v1.35-hml2

Esta cópia é gerada a partir do v1.35 original (`conector.py` `bb2a95e0…`, `conector_nucleo.py` `af8e9e99…`) por `gerar_homolog.py` junto com `bloco_validacao_hml2.py`. O gerador exige esses SHAs. O conector de produção não é tocado: nem os arquivos, nem o registro do Windows, nem o config, nem o log.

| Arquivo | SHA-256 |
|---|---|
| conector_homolog.py | 1cd79249719b6bf4c174d6df0d17bf2afe5d5e00940a2316181fc9ffc43140fb |
| conector_nucleo_homolog.py | 62d8293eafde270100a5870f1127c2f90981d8cb4d241eeaf57944d34138b3cf |

## Mudanças em relação à v1.35
| # | Mudança | Por quê |
|---|---|---|
| H1 | `API_BASE` aponta para `https://homolog-homolog.up.railway.app`. A **trava de rede** tem duas barreiras: `Session.request` (confere o host e força `allow_redirects=False`) e `Session.send` (confere de novo toda requisição preparada, inclusive as de `resolve_redirects`). Só passa https no host homolog. | Na v1.35 a produção estava fixa no código. Na hml1 a trava olhava só a primeira URL, e o requests segue redirecionamentos via `send` com o corpo intacto em 307/308. |
| H2 | Janela "BotTested Conector HOMOLOG v1.35-hml2" | Para não confundir com a de produção. |
| H3/H4 | Log e config próprios (`~\BotTested_Conector_HOMOLOG_*`) | Sem isso, o token salvo e o cache da produção seriam sobrescritos. |
| H5 | Autostart e `bottested://` desligados | Não sequestra as entradas da produção no registro. |
| H6 | O token vai no corpo, pelos gêmeos POST da api 7.79 | Token fora de URL e de log. |
| H7 | Veredito recusado vai para o log (403 BT-V01 / 409 BT-V02) | Na v1.35 era engolido. |
| H8 | MT5 fixado à mão e radar desligado | Nunca troca sozinho de instalação. |
| H9 | Porta de instância única 50574 | A produção usa 50573. |
| H10 | `validar_pendente` estrito (detalhes abaixo) | O veredito tem que corresponder a uma compilação real. |
| H11 | Nenhum fragmento de token ou argv no log | Na v1.35 saía `token {tok[:8]}…`. |

### H10: quando aprova e quando não aprova
1. **Conferência DEMO antes de qualquer job.** O botão "🔎 Conferir MT5 DEMO" faz o seguinte:
   - lê o diário da instalação fixada (`<terminal>\logs\*.log`, linha `'<login>': authorized on <servidor>`, com `config\common.ini` como reserva);
   - lê o último registro de `automated trading is enabled/disabled`;
   - **exige** que você confirme visualmente na janela do MT5.
   A confirmação vale só nesta sessão e só para essa instalação e essa conta. Ela é refeita a cada job. Enquanto não houver confirmação, **o job nem é buscado**: fica "validando" na nuvem e a janela mostra o motivo.
   - D01: nenhum MT5 fixado.
   - D02: conferência pendente.
   - D03: o servidor não tem "Demo" (ou tem "Live"/"Real").
   - D04: a conta mudou.
   - D05: AutoTrading ligado.
2. **`pre_validado` é ignorado.** O servidor já força `False` para o MASTER, e o teste 6 prova isso mesmo com o cache aprovado.
3. **O MetaEditor usado é só o da própria instalação DEMO** (via `origin.txt`), ou o caminho que você puser à mão em `"metaeditor_hml"` no config HOMOLOG. Ele compila com `/inc:<MQL5 da DEMO>`.
4. **Só aprova se tudo abaixo for verdade:**
   - o `.mq5` em disco é idêntico ao do job (SHA-256);
   - o `<bot>_compile.log` é **novo** (o antigo é apagado antes) e tem a linha `N errors` com N = 0;
   - o log cita o `.mq5` do job;
   - o `.ex5` foi **criado depois** do início da compilação (o antigo também é apagado antes).
5. **Casos de falha:**
   - sem MetaEditor, ou MetaEditor que não executa: veredito **falso**, com o log começando por `INDISPONIVEL (não é aprovação)` (M01/M02/M03);
   - erro de compilação ou prova faltando: veredito **falso** (C01–C05).
   Não existe mais aprovação por checagem de sintaxe.

## Instalação no PC (Windows, ao lado da produção)
1. Crie `C:\BotTested_HOMOLOG\` e copie para lá `conector_homolog.py` e `conector_nucleo_homolog.py`, sem renomear.
2. Confira os hashes no PowerShell. Eles têm que bater com a tabela acima:
   ```powershell
   Get-FileHash C:\BotTested_HOMOLOG\*.py -Algorithm SHA256
   ```
3. Instale a dependência com `py -m pip install requests`. O Python precisa ter tkinter; o instalador oficial do python.org já vem com ele.
4. Abra o MT5 **DEMO** e deixe o **Algo Trading desligado**.
5. Rode `py C:\BotTested_HOMOLOG\conector_homolog.py`. O título da janela tem que dizer "HOMOLOG v1.35-hml2".
6. No seletor "Qual MT5 usar", escolha a instalação DEMO. Ela fica fixada.
7. Clique em **🔎 Conferir MT5 DEMO**. Confira na janela do MT5 o login, o servidor Demo e o Algo Trading OFF, e responda "Sim".
8. Na plataforma **homolog**, faça: Editor → nome do bot → 🔑 Gerar token. Cole o token no conector HOMOLOG e clique em **Conectar**.
9. **Só depois de o conector estar online**, clique em Enviar.
   - Se ele estiver offline, a plataforma chama `bottested://`, e isso abre o conector de **produção**.
   - Não use o botão "Já tenho o conector".
10. Evidências para coletar no MT5 demo (`MQL5\Experts\`):
    - `<bot>.mq5`, `<bot>_compile.log` (0 errors) e `<bot>.ex5`;
    - `job_id`;
    - o trecho do log abaixo;
    - print da janela do MT5 com a conta Demo e o Algo Trading OFF;
    - o bot arrastado no gráfico (com Algo Trading OFF), para gerar o snapshot do mesmo magic no Monitor.
    ```powershell
    Select-String -Path "$HOME\BotTested_Conector_HOMOLOG_debug.log" -Pattern "HOMOLOG|veredito|BLOQUEADO|RECUSADO"
    ```

Para remover a cópia, basta apagar a pasta e os dois arquivos `~\BotTested_Conector_HOMOLOG_*`. Nada fica no registro.

## hml8 (C27R14 rev.2, 01/out/2026)
A ponte do motor (H14/H15, bloco `ponte_motor_hml8.py`) lê o **leitor do motor** (`motor_ciclos/bt_motor_leitura_hml.py`)
em `BT_CV_ESPELHO` (SAUDE.json + ATUAL.json + barras/), confere conta, símbolo, instalação MT5 fixada, barra M15 e OHLC
contra a linha do EA, e o fuso EA × motor; só então assina (assinador v0.4). A saúde vai sempre em `detalhe.cv_motor`.
Regerar: `python gerar_homolog.py` (troca exata com assert; originais conferidos por SHA-256). Testes: `test_conector_homolog.py`
(19, contra a bancada isolada; o motor roda de verdade sobre o MetaTrader5 FALSO de `motor_ciclos/testes/fake_mt5`).
