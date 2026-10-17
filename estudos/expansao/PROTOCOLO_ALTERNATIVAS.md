# Protocolo — alternativas de percepção (escrito ANTES da medição, 17/10)

Motor em operação (bt_ciclo_v1, homolog) NÃO é alterado. As alternativas são reimplementadas no estudo, cada uma
trocando UMA peça do motor atual (A0); o resto fica idêntico.

## Dados e cortes cronológicos
| Ativo | Desenvolvimento (escolha de parâmetro) | Validação | Reserva final (só leitura) |
|---|---|---|---|
| BTCUSD M15 | 09/08/2025 → 08/02/2026 | 08/02 → 08/05/2026 | 08/05 → 08/08/2026 |
| XAUUSD M15 | 04/09/2025 → 04/03/2026 | 04/03 → 04/06/2026 | 04/06 → 04/09/2026 |
Parâmetros são escolhidos SÓ no desenvolvimento, por ativo, com n ≥ 30. Validação e reserva só reportam.

## Registro de cada evento
ativo, detector, tipo, direção avaliada (+1 compra / −1 venda), instante de reconhecimento (fechamento da barra M15
de decisão = abertura + 15 min, horário da corretora), preço inicial (fechamento dessa barra), ATR14 do M15 nessa barra,
horizonte H = 16 barras M15, barreiras ±1 ATR. Resolução: primeira barreira tocada. Barra M15 que toca as duas:
resolvida pela sequência das barras M5 e, se ainda empatar, M1 (só XAUUSD tem M1/M5; BTCUSD marca "ambígua").
Sem toque em H = "sem resolução". Os três casos são contados à parte e nunca entram como acerto ou erro.

## Contador de perna (§4.3)
Desenho: "Barras consecutivas na mesma direção sem respiro, por andar" (L = 20 [REF], fonte "Brooks 20–30 barras").
A0 (motor): conta velas consecutivas da mesma cor. A1: conta barras desde o último pivô CONTRA a perna já CONFIRMADO
(N = 2: o pivô em k só existe a partir de k+2), na direção do canal EMA20 do M15 (respiro = pivô contrário confirmado).

## Alternativas (cada uma isolada contra A0)
- A1 perna por pivô: o "contexto tardio" da exaustão usa L_pivô ≥ Lp (Lp ∈ {8, 10, 12, 15, 20}) no lugar de L.
- A2 exaustão exigente: exaustão só conta se o gatilho for rejeição (E2) ou gradual (E3), ou se a escada chegar ao 3º sinal.
  Variantes: A2a = E2/E3 ou 3º sinal; A2b = só 3º sinal.
- A3 confirmação exigente: rompimento pendente só confirma quando uma barra seguinte FECHA além do extremo da barra que
  rompeu (A0: basta a máxima/mínima ultrapassar).

## Avaliação 1 — percepção (verdades definidas aqui, antes de medir)
População P1 (pausa × exaustão): toda barra M15 contrária à perna em curso (canal EMA20 do M15 na barra anterior
= +1 e barra vermelha, ou −1 e barra verde). Extremo da perna E = máxima (perna de alta) / mínima (baixa) desde o último
pivô contrário confirmado (mín. 5, máx. 60 barras) até a barra de decisão.
  Verdade CONTINUA = E é ultrapassado em até H barras. Verdade FIM = E não é ultrapassado em H barras.
  Rótulo do detector: "exaustão" se a escada estiver no 2º sinal ou acima contra a perna na barra; senão "pausa".
  Métricas: precisão = P(FIM | exaustão); taxa de base P(FIM) na população; ganho = precisão − base; cobertura.
População P2 (rompimento): toda primeira barra que fecha fora de uma caixa ativa do M15 (pendente).
  Verdade SUSTENTADO = antes de fechar de volta dentro da caixa, o preço anda 1 ATR além da fronteira rompida, em H.
  Verdade FALSO = fecha de volta dentro antes disso. Outros = sem resolução.
  Métrica: P(SUSTENTADO | confirmado pelo detector) contra P(SUSTENTADO | todos os pendentes); confirmados perdidos.

## Avaliação 2 — efeito operacional
Posição existente no sentido da perna (P1) ou no sentido do rompimento (P2), a partir da barra de decisão:
- exaustão (cortaria): "proteção útil" = −1 ATR antes de +1 ATR; "saída prematura" = +1 ATR antes de −1 ATR.
- pausa (manteria): "continuidade preservada" = +1 ATR antes; "exposição" = −1 ATR antes; excursão contrária máxima em H.
- rompimento: entrada no confirmado; custo de esperar = distância (em ATR) entre o fechamento pendente e o confirmado.

## Dependência, recortes, incerteza
Eventos do mesmo detector a menos de H barras do anterior contado são agrupados (conta só o primeiro); reporto bruto e
agrupado. Intervalo de 95% por bootstrap em blocos semanais. Recortes: ativo, direção, regime do H1 (canal EMA20 do H1
fechado: a favor da perna / contra / lateral). Gráficos: acertos e erros reais com barreiras e extremo.
Linguagem: nada além do que a medição sustenta.
