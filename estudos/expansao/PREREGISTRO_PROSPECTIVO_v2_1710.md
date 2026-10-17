# Pré-registro — validação prospectiva da percepção (estudo v2), fixado em 17/10/2026 antes de qualquer dado novo

Nada aqui emite comando. O motor em operação (A0, bt_ciclo_v1 sha256 9ac1af94…) e a configuração da DEMO (sel-7, gestao-5) não mudam.

## Versão congelada
- Código do estudo: `alternativas.py` aad88abe…, `validacao_v2.py` cd95076f…, `fidelidade.py` a2ac13f2… (cópia no projeto/ambiente).
- Qualquer mudança em parâmetro, verdade, população ou métrica depois de ver dado novo = versão v3, com novo pré-registro e nova janela prospectiva. Os dados já vistos não contam para a v3.

## Dados prospectivos (ainda não vistos)
- BTCUSD: barras M15 (e M5/M1 para desempate) a partir de 08/08/2026 18:45 (corretora) até a data do export.
- XAUUSD: a partir de 04/09/2026 23:45 (corretora).
- Fonte: export do MT5 da DEMO 52648209 (mesmo formato dos arquivos de "Test 12meses"), feito pelo dono. A coleta ao vivo da homolog (auditoria_candles) tem lacunas e só serve de conferência.
- Primeira avaliação quando cada ativo tiver ≥ 30 exaustões agrupadas do A0 (ritmo observado: ~18/mês no BTC, ~17/mês no ouro).

## Hipóteses e critérios de aceitação (fixos)
H1 — percepção do A0: na população de barras contrárias à perna, a precisão "extremo não renovado em 16 barras" quando o A0 lê exaustão supera a taxa de base.
  Aceita no ativo se: n ≥ 30 exaustões agrupadas, diferença pontual ≥ +5 pp E limite inferior do IC 95% conjunto (blocos semanais) > 0.
  Inconclusiva se o IC inclui 0. Rejeitada se o limite superior < 0.
H2 — efeito operacional do corte na exaustão do A0 (posição no sentido da perna, ±1 ATR, 16 barras, ambíguas e sem resolução fora):
  descritiva; "proteção útil" só é afirmada se o limite inferior do IC 95% de P(−1 ATR antes) > 50%.
H3 — rompimento: a regra A0 fiel ao motor (caixa rearmada abandona o rompimento) é comparada com A3 pela entrada no confirmado (+1 ATR antes de −1 ATR).
  A3 só é preferível se a diferença pareada A3 − A0 tiver IC 95% > 0 E os sustentados não confirmados não aumentarem mais que 50%.
Alternativas em sombra (cada uma isolada contra A0, mesmas barras): A1 com Lp = 12 (Lp = 20 equivale ao A0), A2a, A3.
  Uma alternativa de percepção só vira proposta se, no ativo, (alt − A0) na precisão tiver IC 95% pareado > 0 com n ≥ 30, cobertura ≥ 50% da do A0
  e o efeito operacional não piorar mais de 5 pp. Não se exige o mesmo parâmetro nos dois ativos; diferença entre ativos precisa vir com estabilidade nos
  dois períodos prospectivos (primeira e segunda metade).
Não se escolhe pela maior porcentagem isolada.

## O que está fora deste pré-registro
P1, P2, P3a, P3b, P4, item 6 do checklist, D2 — continuam com suas pendências próprias. C5, C6, C7, D1, D3 não são revistos por este estudo.
