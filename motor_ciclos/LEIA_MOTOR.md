# Motor dos Ciclos — instalação reproduzível (homologação)

Origem: `CORRECAO_P2_CICLO_VIVO_27SET.zip` (SHA-256 `bd33c34a3cb5a8b99c7e487710d29dd1cf025d14c276e30ea744328b8d927b4c`). Antes de qualquer cópia, conferi o zip e o manifesto interno: 145 arquivos, todos batem.

## 1. Componentes e hashes

| arquivo | versão | SHA-256 | origem / estado |
|---|---|---|---|
| bt_ciclo_v1.py | CV1 2.4 | 9ac1af947587acaa0a2da56e4d1d9aad75e9217070384fca97f39fe48695077d | congelado 20/set, sem alteração |
| bt_vivo_sombra.py | 7.4 | 47a2ade727a2f72d47761dd4069e45a5f1930e74c9c6d795066b96b1a96f505b | congelado; só `puxar_e_espelhar` é usada |
| bloco1_motor_v3.py | 3.2.B | f6bff47b62d79b8e6fb8b22455493350a134bd970bca91bdb412a5a45812f0f7 | só para o import do vivo_sombra; sem alteração |
| professor_cards_v19.py | 2.0 | bb3e33afaed392c062bc1cc9071588cc34bd579180a35cade3ced8dca647b932 | só para o import; sem alteração |
| professor_bloco2.py | 1.7 | fa84b37eb9d60c92ee3aa73262f32e77bd4804afb33d4d0ac98cfb71bd796b32 | só para o import; sem alteração |
| professor_bloco3.py | 0.5 | adc6f1f85221ea334d2b70b6dacebbb0b0611329066a198ee98f069389f616f8 | só para o import; sem alteração |
| bt_cv_atestado.py | 1.2-c27r6 | ea94366adbbb2edb93802e98657498c3410ba29f33f15a49b45d52be970f6185 | o mesmo arquivo da API (raiz do repositório) |
| bt_ponte_ciclo_v1.py | **1.1-hml** | ver MANIFESTO | correções C1–C3, descritas na §3 |
| bt_conector_atestado.py | **0.4-hml** | ver MANIFESTO | vínculo do bot, fuso e frescor |
| bt_motor_leitura_hml.py | **1.1-hml** | ver MANIFESTO | novo: o leitor; só lê e nunca envia ordens |
| referencia_27set/* | v1.0 / v0.3 | 89e4b4be… / 71b34a58… | originais do pacote, mantidos para o diff |

Dependências: Python ≥ 3.10, `pandas`, `numpy` e `MetaTrader5`. Ver `requirements_motor.txt`.

O pacote também traz `bt_vivo_sombra_v74_c27r.py` (7.4.1-c27r, sha cec5ee18…). A função de espelho dele é idêntica byte a byte à da 7.4: sha256 do corpo de `puxar_e_espelhar` = `7b40826168ea387b…` nas duas. Uso a 7.4 congelada.

## 2. Mapa funcional (código lido: bt_ciclo_v1 v2.4)

| função | onde | situação |
|---|---|---|
| Ciclo 2 (referência D1×H4) | `avaliar` l.391–415, `topdown` | Implementado. O veredito (autorizada/neutra/bloqueada) é a autoridade levada pelo atestado. |
| Ciclo 1 (escada M1→M5→M15) | janela 10→15 l.361–375, `estado_unico` l.378–388, `fases_propagacao` l.562–616 | Implementado. O vivo_sombra só usa no corte; agora vai em telemetria (`cv_motor`). No atestado vão apenas as direções M1/M5/M15. |
| Topos/fundos | `pivos` l.141 (fractal N=2) | Implementado. Agora em telemetria (estrutura, último topo e último fundo por TF). |
| Compressão/expansão | `compressao` l.186 (4 testes), `caixa_estado` l.204, volatilidade em `ficha_tf` l.519 | Implementado. Agora em telemetria (caixa, regime, volatilidade). |
| Lateralidade | `dir`=0 dentro do canal; regime "lateral"/"compressao" | Implementado. Agora em telemetria. |
| Pullback | `classificar_contrario` l.658, `classif` "pullback_presumido" l.417 | Implementado (narrado). Agora em telemetria (classificação). |
| Reversão | `exaustao` E1/E2/E3 + degrau da escada l.244; `reversao_identificada` | Implementado. O vivo_sombra usa no corte `reversao_Nsinal`; agora em telemetria. |
| Canal | EMA20 da máxima e da mínima, `Andar._derivados` l.114 | Implementado; é a base do `dir`. |
| OTT | — | Não existe no motor. Não foi criado. |
| Força | `ficha_tf` l.526 (0–100, [REF]) | Implementado, ainda não medido. Agora em telemetria. |
| Ranking | — | Não existe no motor. Não foi inventado. |

## 3. Correções da integração (as regras do motor não mudaram)

- **C1 — fuso.** O espelho guarda o horário do servidor da corretora (o campo `time` do `mt5.copy_rates`). A ponte v1.0 tratava esse horário como UTC, o que faria o atestado nascer 3h no futuro. Agora a ponte faz `ts_barra_m15(UTC) = abertura_corretora + 15 min − off_corretora_s`.
  - O fuso de referência vem do EA (TimeCurrent − TimeGMT).
  - O leitor mede o próprio fuso pelo tick, e o conector recusa a assinatura se os dois divergirem.
- **C2 — vínculo do bot.** A API exige `bot_token_hash` desde a c27r6; a v1.0 não emitia esse campo. Agora o assinador calcula sha256 do token. O token não é gravado em lugar nenhum.
- **C3 — frescor.** A ponte não assina barra fechada há mais de 900 s nem barra no futuro.

Divergência mantida, conforme a radiografia de 27/set: o motor autoriza com D1=H4=M15, e a API ainda exige M1/M5/M15 todos no lado. O efeito é fail-closed: a integração nunca opera mais do que o motor permite.

## 3b. Origem exata de cada critério que pode autorizar uma abertura

| critério | quem calcula | campo ASSINADO no atestado | entra na autorização? |
|---|---|---|---|
| **Ciclo 2 — referência** (D1 e H4 contra a direção do M15) | motor, `bt_ciclo_v1.avaliar` l.391-415 → `12_veredito.topdown` | `cv1.veredito` (autorizada/neutra/bloqueada) + `cv1.motivo`; os insumos em `cv2.dirs.D1`, `cv2.dirs.H4`, `cv1.janela.M15` | **sim**: bloqueada = veto, neutra = não autoriza, autorizada segue |
| **Ciclo 1 original** (escada M1→M5→M15, janela 10→15, fases) | motor, l.361-388 + `fases_propagacao` | **nenhum** (só telemetria `cv_motor`) | **não**; o motor usa a janela 10→15 só para corte de posição aberta |
| **Checagens adicionais da API** | `_r01_ler_ciclos_servidor`, `_r01_emitir_decisao`, RPC `r01_claim_e_comando` | usa `bot_token_hash`, `simbolo`, `magic`, `ts_barra_m15`, `assinatura` e `cv1.janela.M1/M5` | **sim**: HMAC + vínculo + barra fechada + validade de 900 s; **M1 e M5 no lado do M15**; lado do comando = lado da decisão; idempotência por (bot, barra, lado) e consumo único |

`cv1.veredito` tem esse nome por legado do contrato c27r3, mas carrega o **topdown do motor**, que é o critério do Ciclo 2. `cv1.janela` são as direções do canal EMA20 (`le["dir"]`) do motor, não a escada do Ciclo 1.

**Divergência motor × API** (regra `R-CICLO-01.divergencia_motor_api`): o motor autorizou (D1 = H4 = M15), mas M1 e/ou M5 não acompanham, e a API veta. Na BabyMachine isso aparece com motivo e classe próprios, separado de falha de integração:
- `R-CICLO-01.atestado` = atestado ausente ou recusado;
- `R-CICLO-01.incoerente` = "autorizada" com D1, H4 ou M15 fora do lado, combinação que o motor nunca produz.

## 4. Operação no PC (somente homologação e conta demo)

```
py C:\BotTested_HOMOLOG\motor\bt_motor_leitura_hml.py --ativo XAUUSD --login <conta demo> ^
   --terminal "<terminal64.exe da instalação demo>" --dados C:\BotTested_HOMOLOG\motor\dados
```

**Variáveis de usuário:**
- `BT_CV_ESPELHO=C:\BotTested_HOMOLOG\motor\dados`
- `BT_CV_MOTOR_DIR=C:\BotTested_HOMOLOG\motor`
- `BT_CV_SEGREDO` — o mesmo valor do Railway homolog. É digitado mascarado no instalador e conferido pela impressão `/conector/cv-impressao`.

**Início:** pelo atalho `BotTested_HOMOLOG_Motor.cmd` na pasta Inicializar do Windows (criado pelo `instaladores/instalar_motor_hml8.ps1`, sem precisar de administrador), que roda `motor_iniciar.cmd`; o .cmd religa o leitor 30 s depois de qualquer queda (log em `dados\leitor.log`). Também pode ser rodado à mão. Ele recusa subir se:
- a conta não for DEMO;
- o login for diferente do informado;
- o terminal não existir.

**Reinício:**
- a pasta de cada barra é imutável e `ATUAL.json` é trocado de forma atômica;
- ao subir de novo, a barra já publicada não é republicada;
- a API grava uma linha por barra (bot, barra_m15);
- decisões só nascem pelo emissor R-CICLO-01, idempotente por (bot, barra, lado), com consumo único pela RPC.

**Saúde:** `SAUDE.json` é gravado a cada 20 s. O conector marca `processo_parado` quando passa de 90 s sem batimento.

**Estados:** a BabyMachine mostra cada estado da cadeia — `processo_parado`, `espelho_atrasado`, `identidade_divergente`, `fuso_divergente`, `assinatura_recusada` — e qual elo falhou.

**Ordens:** nenhuma.
- O leitor substitui `mt5.order_send` e `order_check` por erro antes de carregar o motor.
- Não chama `sombra()`, `executar()`, trailing nem proteção.
- O `bt_vivo_sombra` com `--executa` NÃO deve rodar junto. O instalador verifica isso e para se ele estiver rodando.

## 5. Desativar e restaurar

`powershell -ExecutionPolicy Bypass -File .\instaladores\desinstalar_motor_hml8.ps1 [-RemoverSegredo] [-ReabrirConector]`
- Para o leitor e remove o `BotTested_HOMOLOG_Motor.cmd` da pasta Inicializar.
- Restaura o conector do `_backup_<data>` registrado em `instalacao_hml8.json`.
- Devolve `BT_CV_ESPELHO`/`BT_CV_MOTOR_DIR` aos valores anteriores, ou remove se não existiam.
- `BT_CV_SEGREDO` só é removido com `-RemoverSegredo` e se não existia antes da instalação.
- Move `C:\BotTested_HOMOLOG\motor` para `_desinstalado_<data>`; nada é apagado.

Só desligar o início automático, sem desinstalar: apagar
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\BotTested_HOMOLOG_Motor.cmd` e fechar a janela "BotTested HOMOLOG Motor".

## 6. Canal de comando (Conector HOMOLOG hml9, C27R16)

O conector v1.35 nunca teve a perna que leva o comando da nuvem ao EA. Em produção, os 46 comandos já criados ficaram todos em `pendente`, sem entrega nem confirmação. O hml9 implementa essa perna, só para homologação e conta demo.

| etapa | quem faz | onde fica registrado |
|---|---|---|
| sinal de entrada | detector da plataforma (`_detectar_oportunidade`), a cada snapshot, com modo `copiloto` ou `automatico` | oportunidade no card do Monitor |
| decisão | `_r01_emitir_decisao`: atestado assinado do motor + checagens da API | `ciclo_decisoes` (emitida) |
| consumo único + comando | RPC `r01_claim_e_comando` | `ciclo_decisoes` (consumida) + `mt5_comandos` (pendente) |
| entrega | conector hml9: `POST /mt5/comando/pendente/checar` e grava `MQL5\Files\bt_cmd_<magic>.txt` | `mt5_comandos` (entregue) + trilha `comando` |
| execução | EA (`BTLerComando`): `OrderSend` e grava `bt_ok_<magic>.txt` | diário do MT5 (`BOTTESTED_CMD`, `BOTTESTED_CMD_OK`) |
| resposta | conector: `POST /mt5/comando/confirmar` com ticket, preço e retcode | `mt5_comandos` (executado ou falhou) + trilha `resposta_mt5` |
| posição | EA: evento `aberto` e snapshot com a posição | BabyMachine + Monitor |

Travas do conector:
- só busca comando com a DEMO conferida e o EA com snapshot fresco (menos de 35 s);
- abertura sem decisão dos Ciclos (`decisao.id` + `uid`) não é entregue;
- comando expirado não é entregue;
- cada id é entregue uma única vez por instalação (registro em `bt_hml_comandos_entregues.json`);
- EA não consome em 20 s: o arquivo é retirado e o comando falha com o motivo;
- EA consome e não responde em 45 s: falha declarada como "estado desconhecido", sem reenvio;
- retcode diferente de 10008/10009 é falha, mesmo que o EA escreva "ok";
- o conector não envia ordem: só o EA chama `OrderSend`.

A confirmação na API passou a exigir o token do bot dono do comando. Antes bastava o id.
