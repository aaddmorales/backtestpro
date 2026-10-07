# C27R24 — Sessão de ensaio, dois ativos e limites comuns (homologação / DEMO)

API 7.93 · app v10.60 · leitor 1.6-hml · conector v1.35-hml12 · sql/0011. Nada em `main`, produção ou conta real.
Código congelado (bt_ciclo_v1, bloco1_motor_v3, professor_cards_v19, professor_bloco2, bt_vivo_sombra, bt_cv_atestado,
bt_conector_atestado, bt_ponte_ciclo_v1) **não foi alterado**.

## 1. Sessão de auditoria

| O quê | Como |
|---|---|
| Identidade | `sessoes_teste.id` (texto único), bots, `inicio`, `primeira_barra`, `fim_previsto`, `fim`, `config` (limites) |
| Carimbo | coluna `sessao_teste_id` em `ciclo_leituras`, `ciclo_trilha`, `selecao_avaliacoes`, `ciclo_decisoes`, `mt5_comandos`, `babymachine_operacoes` (+ `relatorios_gerados`), posta por **gatilho do banco** no INSERT e imutável depois |
| Histórico anterior | linhas sem carimbo. Nada é apagado; a contagem e a impressão do histórico ficam em `sessoes_teste.preservacao` |
| Três classes | **do ensaio**: barra M15 de referência ≥ `primeira_barra` (ou, sem barra, gravado depois do início) · **anterior**: barra em curso no início ou anterior · **anterior recebido com atraso**: barra mais antiga gravada depois do início (`sessao_atraso_de`) |
| Recorte | no backend: `/learning/ciclos/ao-vivo`, `/learning/ciclos/trilha`, `/babymachine/operacoes`, `/learning/relatorio/gerar` (todas as consultas do relatório) e `/learning/sessao/painel`. Padrão = sessão do bot; `anterior`; `tudo`; ou o id |
| Contadores | uma função do banco (`sessao_contadores`) alimenta tela, JSON e PDF |
| Reinício | o recorte é uma coluna gravada: reiniciar API/conector/leitor ou recarregar a página não zera nem duplica (UNIQUE por barra continua valendo) |

## 2. Dois ativos

Um leitor por ativo, cada um em `dados\<ATIVO>`; a ponte do conector escolhe a pasta pelo símbolo do EA. Nada passa de um
ativo para o outro: barras, sinais, estudo (`estudo_biblioteca_v2` por ativo), ficha de spread/ponto do código congelado,
limites de spread/desvio por símbolo e **especificação do símbolo** (assinada) são de cada um.
Horários de sessão: a API Python do MT5 não os expõe — ficam "não registrado"; o estado de negociação vem do modo de
negociação e da idade do último tick. Sem barra nova, o estado é registrado na trilha (`mercado`) e a sessão espera.

## 3. Cadeia de abertura (só dentro da sessão)

1. seleção `sel-3` escolhe o candidato da barra (M15/M30/H1; D1/H4 = contexto, sem veto automático);
2. autoridade `r01v5`: 12 condições sobre o candidato **assinado**;
3. travas de execução: chave `autoridade_contratos.r01v5` ligada **e** sessão ativa com `aberturas_habilitadas`
   (o modo operacional legado do bot não participa; bots ficam em *observar*, e o detector/protetor legados não atuam em bot de sessão);
4. plano de lote pelo risco: `min(0,10% do patrimônio, US$ 10)` ÷ perda por lote (distância ao stop ÷ tick × valor do tick,
   da especificação assinada), arredondado **para baixo** no passo; se o lote mínimo não cabe, não abre;
5. limites comuns conferidos e **reservados na mesma transação** (`sessao_reservar`): 6 aberturas, 1 posição por ativo,
   2 simultâneas, risco agregado US$ 20, 3 perdas seguidas, US$ 30 de perda realizada, término previsto;
6. decisão emitida → consumo único (`r05_claim_e_comando`) → comando com o stop assinado e o lote do plano.

## 4. Gestão e saída (contrato do estudo, `gestao-1`)

Ordem do `professor_bloco2.rodar_seletor`, uma avaliação por barra M15 fechada: stop (na corretora) → B5 → B3 (posição com
2+ barras) → corte do Ciclo → trailing estrutural (pivô ∓ 0,3×ATR14, só aperta). Leitura feita pelo leitor com o código
congelado, assinada no atestado de candidatos; a API emite `close`/`mover_sl` (origem `sessao_gestao`, um por posição×barra×tipo).
Sem alvo fixo. No término previsto: novas aberturas suspensas; a gestão continua; a sessão encerra quando não resta posição.

**Diferença declarada:** o EA tem um trailing próprio por barra (`InpBTTrailingBarra`, ligado por padrão). Se ele mexer no
stop, o livro registra "alterado FORA da plataforma". Para seguir só o contrato do estudo, desligue esse parâmetro no EA.

## 5. Resultado

Realizado = lucro + comissão + swap dos **negócios do MT5** da posição (lidos pelo leitor, assinados pelo conector).
Posições de outros magics: fora do resultado; aparecem na exposição e a margem livre da conta entra no plano.
Saldo e patrimônio são da conta: aparecem uma vez no consolidado.

## 6. Evidência

- Bancada (sintético, ambiente isolado): `testes/test_sessao.py` (8), `conector_homolog/test_conector_homolog.py::test_h21`,
  `motor_ciclos/testes/test_motor_ciclos.py::test_10`; 168 testes no total.
- Plataforma: ver o relatório de ativação da sessão (identificador, início, bots/magics, versões e configuração efetiva).
