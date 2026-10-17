# Protocolo de validação da percepção do Ciclo — v3 (BabyMachine)

Ordem do dono 17/10/2026 18:57 Kyiv — "consolidar a auditoria e corrigir o protocolo de validação". **Nenhuma mudança estratégica:** A0 (motor `bt_ciclo_v1`), sel-7 e gestao-5 continuam como estão; nenhum parâmetro novo. Este arquivo substitui o `PREREGISTRO_PROSPECTIVO_v2_1710.md` (que confundia "comparação temporal" com dado prospectivo).

## 1. Congelamento

- **Instante de congelamento = instante do commit que contém este arquivo** (`git log -1 --format=%cI -- estudos/expansao/PROTOCOLO_VALIDACAO_v3.md`, em UTC). O valor exato vai registrado no documento do projeto e no bloco de publicação.
- **A janela prospectiva começa na primeira barra M15 que ABRE depois do congelamento.** Nada antes disso é prospectivo.
- Qualquer mudança neste arquivo, no código da seção 2 ou nos critérios da seção 6 = **nova versão do protocolo, com novo congelamento**; o que já tiver sido coletado vira dado exposto (classe B) para a versão nova.

## 2. Versões, hashes e configuração congelados

| Item | Valor |
|---|---|
| Motor do Ciclo (A0) | `motor_ciclos/bt_ciclo_v1.py` sha256 `9ac1af947587acaa0a2da56e4d1d9aad75e9217070384fca97f39fe48695077d` (parâmetros §11 [REF] do próprio motor; N pivô 2, H 16 barras M15) |
| Em operação na homolog no congelamento | API 8.27-c27r55c (commit bf0e0a3, implantada 17/10 03:03:26Z), sel-7, gestao-5, leitor 1.10, conector HOMOLOG v1.39-hml17, EA eav 7.83. A API 8.28 pendente é só relatório (não muda nenhuma regra) |
| Estudo — reconstrução | `alternativas.py` `aad88abeeff0189191d5bf27f8b8d4dd9333d83bb35059aa90f86215b5e4e9fd` |
| Estudo — validação v2 (bootstrap semanal, recortes) | `validacao_v2.py` `cd95076fa179f7791eea904007bf58d89c8c40f2bb4ccdd6562c0ea4eb501234` |
| Métrica primária v3 | `metrica_v3.py` `7e0a309a4062d9c391429e3a6a36e8009ed723ab63cee3dc526aa5328314457a` |
| A0 × A3 pareado | `a3_pareado.py` `59b03d0649936c76e80d746d221d0b82244cacbbfb567104683638d88c97ec62` |
| Fidelidade estudo × motor | `fidelidade.py` `a2ac13f2ff199b8394dcee76a807d1c348effd2f8e10968c5477d3c3a4247244` |
| Auditoria de contadores | `auditoria_eventos.py` `7989a7379b4eb851f1ee61e759d6422297418769ef4504db2d4e254687057783` |
| Dados históricos usados | `dados_sha256.txt` (8 exportações MT5; os arquivos não estão no repositório) |

Configuração do estudo (já fixada antes, não muda): população P1 = barras contrárias à perna; verdade = extremo da perna renovado ou não em 16 barras M15; P2 = rompimentos pendentes da caixa do motor (com rearme); verdade SUSTENTADO = 1 ATR além da fronteira antes de fechar de volta dentro; desempate de barra ambígua por M5/M1 quando houver.

## 3. Três classes de dados

| Classe | BTCUSD | XAUUSD | Uso permitido |
|---|---|---|---|
| **A. Desenvolvimento (exposto)** | 09/08/2025 → 08/08/2026 18:45 (inclui os trechos chamados "validação" 08/02→08/05 e "comparação temporal" 08/05→08/08) | 04/09/2025 → 04/09/2026 23:45 (idem: 04/03→04/06 e 04/06→04/09) | Exploração e descrição. **Todos os três trechos já foram vistos** (v1, v2, alternativas): nenhum número daqui é evidência confirmatória. |
| **B. Histórico ainda não usado, com exposição parcial** | 08/08/2026 19:00 → congelamento | 05/09/2026 → congelamento | Verificação **secundária e descritiva**. Exposição já ocorrida: operações DEMO desde 29/09 (ensaio), ops 55–71 auditadas barra a barra (15–17/10), `auditoria_candles` 10–17/10 examinada, gráficos das conversas. Não serve como prova prospectiva. As exportações desse trecho ainda não foram feitas. |
| **C. Prospectivo** | 1ª barra M15 que abre após o congelamento → fim da janela (seção 5) | idem | **Única classe confirmatória.** |

## 4. Correções da auditoria que entram no protocolo

1. **Denominadores.** No v2 a "precisão da exaustão" (exaustões agrupadas entre si) era comparada com a "base" (população agrupada separadamente). As duas listas não eram uma subconjunto da outra (ex.: BTC desenvolvimento — 143 exaustões agrupadas, só 20 delas presentes na população agrupada de 996). Métrica v3: **Δ = P(não renovado | exaustão) − P(não renovado | pausa)**, cada rótulo agrupado dentro de si (16 barras), mesma população bruta. Essa troca foi feita depois de ver os números históricos; por isso os números históricos em v3 são descritivos (apêndice) e só o prospectivo decide.
2. **Recortes por direção e regime** passam a ser **derivados da população agrupada única** (somam o total). O v2 reagrupava dentro de cada subgrupo, e por isso os totais não eram aditivos (ex.: BTC desenvolvimento, direção 147 e regime 154 contra 143 no total): dois eventos a menos de 16 barras um do outro sobrevivem ambos quando caem em subgrupos diferentes. Recortes são só descritivos.
3. **Identificadores.** Todo evento P1 tem id `ativo|período|barra M15 de abertura (horário da corretora)|índice` com perna, leitura A0, verdade, se entrou na população agrupada e na exaustão agrupada (`eventos_p1_v2.csv.gz`, 21.096 linhas). O prospectivo gera o mesmo arquivo.

## 5. Datas fixas (sem teste repetido)

- Janela confirmatória: do início prospectivo até **2027-01-16 00:00 UTC (exclusivo)** — 13 semanas.
- **Uma única análise confirmatória**, feita depois de exportar a janela inteira (M15, M5, M1 de BTCUSD e XAUUSD, mesma corretora da conta DEMO), com hash dos arquivos registrado antes de rodar.
- Leituras intermediárias em **2026-11-14** e **2026-12-12**: só integridade (barras faltando, n acumulado, divergências de fidelidade). **O Δ não é calculado nem mostrado nelas.**
- Se um ativo tiver menos de 30 exaustões agrupadas na janela: extensão única, já fixada, até **2027-04-17 00:00 UTC** para esse ativo, com uma única análise ao fim. Sem segunda extensão; se continuar abaixo de 30 → "insuficiente".

## 6. Critérios fechados

Família confirmatória de **4 testes**: (1) Δ A0 BTCUSD, (2) Δ A0 XAUUSD, (3) A3 × A0 BTCUSD, (4) A3 × A0 XAUUSD. Correção de multiplicidade de Bonferroni: as decisões usam **IC 98,75%** (bilateral, reamostragem de semanas ISO, 1.000 reamostras, sementes fixas no código). A1, A2a e A2b ficam fora da família: são descritivas e não podem ser adotadas por este protocolo (n insuficiente; a escolha de Lp teve desempate alfabético).

### 6.1 Percepção A0 (por ativo, separadamente — não se exige o mesmo resultado nos dois)

| Condição | Classificação |
|---|---|
| exaustões agrupadas < 30 | insuficiente |
| limite inferior > 0 **e** Δ pontual ≥ 5 pp | efeito confirmado e relevante |
| limite inferior > 0 **e** Δ pontual < 5 pp | **efeito positivo abaixo do limiar relevante — não aceito** |
| IC contém 0 | inconclusivo |
| limite superior < 0 | contrário |

### 6.2 Operacional

O "corte na exaustão" (±1 ATR) é medida operacional secundária, descritiva; não decide a percepção.

### 6.3 A3 × A0, pareado por oportunidade

- Unidade: cada rompimento pendente do motor (1º fechamento fora da caixa armada). As duas regras são medidas na **mesma** oportunidade.
- Oportunidade em que a regra não confirma (inclusive por rearme/volta para dentro) = **resultado 0** para ela; nenhuma oportunidade sai da conta.
- Cada regra entra no fechamento da sua própria barra de confirmação (horários diferentes são parte do efeito). Resultado em ATR **da barra do rompimento** (mesma unidade nas duas): +1 / −1 / 0 (ambígua sem desempate) / marcação a mercado na 16ª barra.
- Medidas pareadas: d = resultado(A3) − resultado(A0); Δ precisão das confirmações (SUSTENTADO entre confirmados decididos); Δ cobertura (confirmados entre SUSTENTADOS).
- **A3 aceito somente se as três valerem:** (a) Δ precisão com limite inferior > 0 e ponto ≥ 5 pp; (b) **não-inferioridade da cobertura: limite inferior do IC de Δ cobertura > −5 pp** (o requisito "não piorar mais de 5 pp" medido com incerteza, não pelo ponto); (c) d não classificado como "pior" (limite superior < 0). Não há margem em ATR (nenhum limite novo).

### 6.4 Proibido

Trocar métrica, horizonte, barreira, agrupamento, população, datas, família ou níveis depois do congelamento; escolher recorte "que deu certo"; somar benefícios de avaliações da mesma posição.

## 7. Fidelidade antes de analisar

Antes da análise confirmatória, `fidelidade.py` roda na janela prospectiva. Divergência estudo × motor em exaustão, escada, perna ou rompimento pendente tem de ser explicada; havendo divergência, a análise usa o registro do motor.

## 8. Operações reais (auditoria operacional continua aberta)

- **Por avaliação** (`operacoes_reais.json`): cada corte, alerta e proteção contra "manter com o stop vigente antes da decisão" por 16 barras. As avaliações da mesma posição **não são independentes**: os números não se somam entre si.
- **Por operação** (`ops/efeito_por_operacao.json`): uma linha por posição; base fixa = mesma entrada, stop inicial, nenhuma gestão, 16 barras completas. Mede a gestão inteira (trailing + B3 + Ciclo + tempo), não o Ciclo isolado — o efeito isolado do Ciclo **não é determinado**.
- **Atrasos** (`ops/atrasos_marcos.json`): mesmos marcos em todas as versões: fechamento → 1º snapshot → 1º snapshot com atestado válido (o usado) → avaliação → comando → entregue → confirmado. Impacto só onde há evidência; senão "não determinado".

## 9. O relatório final da validação traz

Para cada ativo e teste: classe dos dados, janela exata, hashes dos arquivos exportados, n bruto e agrupado, Δ e IC 95% e 98,75%, classificação pela tabela 6.1/6.3, divergências de fidelidade, e a frase "nenhum critério foi alterado após o congelamento" — ou a lista do que foi alterado e a nova versão.
