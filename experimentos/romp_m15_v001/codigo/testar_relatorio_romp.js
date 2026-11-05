// ROMP-M15-0.1 — o relatório da homologação ISOLADA LOCAL (API 8.29.4/app v10.88.4) exibe os eventos REAIS do executor (terminal simulado) sem erro, separado por versão e classe.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const OUT = process.argv[2]; const CDN = process.env.CDN_DIR; const RES = [];
const reg = (n, nome, ok, det) => { RES.push({teste: n, nome, ok: !!ok, detalhe: det}); console.log((ok ? 'OK ' : 'FALHA ') + n + ' ' + nome + ': ' + det); };
const LOCAL = {'supabase.js': path.join(CDN, 'supabase-supabase-js-2.118.0/package/dist/umd/supabase.js'), 'chart.umd.js': path.join(CDN, 'chart.js-4.4.1/package/dist/chart.umd.js'),
  'lightweight-charts.standalone.production.js': path.join(CDN, 'lightweight-charts-4.1.3/package/dist/lightweight-charts.standalone.production.js')};
(async () => {
  const br = await chromium.launch(); const ctx = await br.newContext({viewport: {width: 1440, height: 1000}}); const pg = await ctx.newPage(); const erros = [];
  pg.on('pageerror', e => erros.push(String(e)));
  await ctx.route('**/*', r => { const u = r.request().url(); for (const [k, f] of Object.entries(LOCAL)) if (u.endsWith(k)) return r.fulfill({path: f, contentType: 'application/javascript'});
    if (u.startsWith('http://127.0.0.1')) return r.continue(); return r.abort(); });
  await pg.goto('http://127.0.0.1:8000/app', {waitUntil: 'domcontentloaded'}); await pg.waitForTimeout(2500);
  await pg.evaluate(async ([e, s]) => { await sb.auth.signInWithPassword({email: e, password: s}); }, [process.env.LM_EMAIL, process.env.LM_SENHA]);
  await pg.waitForFunction(() => typeof usuarioAtual !== 'undefined' && usuarioAtual && usuarioAtual.id, null, {timeout: 20000});
  await pg.goto('about:blank'); await pg.goto('http://127.0.0.1:8000/app#lm', {waitUntil: 'domcontentloaded'}); await pg.waitForTimeout(2500);
  await pg.waitForFunction(() => /eventos/.test(document.getElementById('lmx-estado').textContent), null, {timeout: 20000});
  await pg.selectOption('#lmx-classe', 'simulado'); await pg.waitForTimeout(400);
  const opts = await pg.$$eval('#lmx-versao option', os => os.map(o => o.value)); const vr = opts.find(v => /ROMP-M15-0\.1/.test(v));
  reg('S1', 'versão da experiência aparece separada no filtro de versão', !!vr, `opções: ${opts.filter(Boolean).length}; ROMP: ${vr}`);
  if (vr) await pg.selectOption('#lmx-versao', vr); await pg.waitForTimeout(500);
  await pg.click('button[data-t="ops"]'); await pg.waitForTimeout(400); const t = await pg.textContent('#lmx-aba');
  reg('S2', 'operações da experiência listadas (ids ROMP-XAU)', /ROMP-XAU-2026/.test(t), t.slice(0, 160).replace(/\s+/g, ' '));
  await (await pg.$('#lmx-aba')).screenshot({path: path.join(OUT, 'ROMP_relatorio_operacoes.png')});
  await pg.click('button[data-t="dec"]'); await pg.waitForTimeout(400); const d = await pg.textContent('#lmx-aba');
  reg('S3', 'decisões e impedimentos com condição e motivo da estratégia', /canal de 20|canal de 10/.test(d), d.slice(0, 160).replace(/\s+/g, ' '));
  for (const a of ['res', 'sel', 'exe', 'tf', 'ev', 'hist', 'ctr', 'uso']) { await pg.click(`button[data-t="${a}"]`); await pg.waitForTimeout(250); }
  reg('S4', 'todas as abas abrem com os eventos da experiência sem erro de página', erros.length === 0, `erros: ${erros.length} ${erros.slice(0, 2).join(' | ')}`);
  fs.writeFileSync(path.join(OUT, 'ROMP_teste_relatorio.json'), JSON.stringify({aprovados: RES.filter(r => r.ok).length, total: RES.length, testes: RES}, null, 1)); console.log(`${RES.filter(r => r.ok).length}/${RES.length}`); await br.close();
})();
