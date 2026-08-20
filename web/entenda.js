/* Tela 3 — "Entenda". Página de contexto para quem não é do setor elétrico.
   Todos os números são lidos dos mesmos arquivos que alimentam o mapa, e não
   digitados aqui: se o pipeline reprocessar, esta página acompanha sozinha. */

const Entenda = (() => {
  let carregado = false;

  const fmt = (n, d = 0) =>
    new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);
  const brl = (v) =>
    new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);

  const buscar = (url) => fetch(url).then((r) => r.json()).catch(() => null);

  /* Tarifa final em R$/kWh: os valores da ANEEL vêm em R$/MWh sem tributo. */
  function porKwh(tarifas, faixa) {
    const t = tarifas.tributos;
    return (faixa.te + faixa.tusd) / 1000 / (1 - t.icms_pr - t.pis_cofins);
  }

  async function montar() {
    if (carregado) return;

    const [muni, tarifas, perfis, consumo, irrad, bairros] = await Promise.all([
      buscar("data/municipio.json"),
      buscar("data/tarifas.json"),
      buscar("data/perfis_consumidor.json"),
      buscar("data/consumo_real.json"),
      buscar("data/irradiancia.json"),
      buscar("data/resumo_bairros.geojson"),
    ]);

    // ---------- a cidade ----------
    if (muni && bairros) {
      const num = (v) => Number(v) || 0;
      const ucs = bairros.features.reduce((a, f) => a + num(f.properties.unidades_consumidoras), 0);
      const trafos = bairros.features.reduce((a, f) => a + num(f.properties.transformadores), 0);

      document.getElementById("ent-cidade").innerHTML = `
        <div class="ent-num"><b>${fmt(muni.populacao_censo2022)}</b><span>habitantes<em>IBGE, Censo 2022</em></span></div>
        <div class="ent-num"><b>${fmt(muni.domicilios_estimados)}</b><span>domicílios<em>população ÷ 2,82</em></span></div>
        <div class="ent-num"><b>${fmt(bairros.features.length)}</b><span>bairros<em>malha oficial do IBGE</em></span></div>
        <div class="ent-num"><b>${fmt(ucs)}</b><span>imóveis modelados<em>footprints do OpenStreetMap</em></span></div>
        <div class="ent-num"><b>${fmt(trafos)}</b><span>transformadores<em>estimados, ~30 imóveis cada</em></span></div>
        <div class="ent-num destaque"><b>${fmt(muni.ufv_residencial)}</b>
          <span>casas com energia solar<em>${fmt(muni.taxa_adesao_residencial * 100, 1)}% dos domicílios · ANEEL</em></span></div>`;
    }

    // ---------- perfis da ANEEL ----------
    if (perfis) {
      const linhas = [];
      for (const [classe, bloco] of Object.entries(perfis.classes)) {
        const agrupado = {};
        for (const p of bloco.perfis) {
          const a = agrupado[p.arquetipo] || { n: 0, ponta: 0, oport: p.oportunidade, pico: [] };
          a.n += 1; a.ponta += p.pct_ponta; a.pico.push(p.hora_pico);
          agrupado[p.arquetipo] = a;
        }
        for (const [nome, a] of Object.entries(agrupado)) {
          linhas.push({ classe, nome, n: a.n, ponta: a.ponta / a.n, oport: a.oport,
                        pico: Math.round(a.pico.reduce((x, y) => x + y, 0) / a.pico.length) });
        }
      }
      linhas.sort((a, b) => b.ponta - a.ponta);

      const total = Object.values(perfis.classes).reduce((a, b) => a + b.perfis.length, 0);
      document.getElementById("ent-perfis-intro").innerHTML = `
        Para calcular tarifas, a ANEEL precisa saber como as pessoas realmente consomem ao
        longo do dia. As distribuidoras então instalam medidores em uma amostra de clientes
        e levantam a curva de cada um, de 15 em 15 minutos. O resultado é publicado como
        <strong>“consumidor tipo”</strong>. Para a Copel são <strong>${total} perfis medidos</strong>
        (${perfis.ano_processo}) — não são personas inventadas por nós, e é a base do que o
        mapa mostra.`;

      document.getElementById("ent-perfis").innerHTML = linhas.map((l) => `
        <div class="ent-perfil">
          <div class="ent-perfil-topo">
            <b>${l.nome}</b>
            <span class="ent-perfil-tag">${l.n} perfil(is)</span>
            <span class="ent-perfil-num">pico ~${String(l.pico).padStart(2, "0")}h · ${fmt(l.ponta, 1)}% na ponta</span>
          </div>
          <p>${l.oport}</p>
        </div>`).join("");
    }

    // ---------- tarifa ----------
    if (tarifas) {
      const c = tarifas.modalidades.convencional.unico;
      const b = tarifas.modalidades.branca;
      const conv = porKwh(tarifas, c);
      const fp = porKwh(tarifas, b.fora_ponta);
      const inter = porKwh(tarifas, b["intermediário"]);
      const ponta = porKwh(tarifas, b.ponta);

      document.getElementById("ent-tarifa").innerHTML = `
        <p>A conta de luz não é um preço só. O que você paga por kWh é a soma de duas
        parcelas, definidas pela ANEEL a cada reajuste:</p>

        <table class="ent-tabela">
          <tr><td><b>TE</b> — Tarifa de Energia</td>
              <td>a energia em si, gerada e transportada até a distribuidora</td>
              <td>${fmt(c.te, 2)} R$/MWh</td></tr>
          <tr><td><b>TUSD</b> — Tarifa de Uso do Sistema</td>
              <td>o uso dos fios, postes e transformadores que levam a energia até a casa</td>
              <td>${fmt(c.tusd, 2)} R$/MWh</td></tr>
          <tr class="ent-destaque"><td colspan="2">Somando, e acrescentando ICMS e PIS/COFINS</td>
              <td>${brl(conv)}/kWh</td></tr>
        </table>

        <p>Dentro da TUSD há um componente chamado <b>Fio B</b>
        (${fmt(c.fio_b, 2)} R$/MWh), que remunera especificamente a rede de distribuição.
        Ele é a peça central da regra de energia solar — voltamos a ele adiante.</p>

        <h3>Convencional e branca: dois jeitos de pagar</h3>
        <p>Na <b>tarifa convencional</b> o preço é o mesmo a qualquer hora. Na
        <b>tarifa branca</b>, o preço muda conforme a hora do dia:</p>

        <table class="ent-tabela">
          <tr><td><b>Fora de ponta</b></td><td>madrugada, manhã e tarde</td>
              <td class="barato">${brl(fp)}/kWh</td></tr>
          <tr><td><b>Intermediário</b></td><td>${tarifas.horarios_branca.intermediario.map((h) => h + "h").join(" e ")}</td>
              <td>${brl(inter)}/kWh</td></tr>
          <tr><td><b>Ponta</b></td><td>${tarifas.horarios_branca.ponta[0]}h–${tarifas.horarios_branca.ponta.at(-1) + 1}h, quando todo mundo chega em casa</td>
              <td class="caro">${brl(ponta)}/kWh</td></tr>
        </table>

        <p class="ent-nota"><b>A branca nem sempre compensa.</b> Ela só vale a pena para
        quem consegue tirar consumo do horário de ponta. Quem tem pico noturno — o perfil
        mais comum — costuma pagar <em>mais</em> na branca. É por isso que o painel de cada
        imóvel compara as duas: a resposta depende do perfil, não é a mesma para todos.</p>

        <h3>Por que a ponta é mais cara</h3>
        <p>Não é arbitrário. A rede precisa ser dimensionada para o momento de maior
        demanda do dia. Se todos ligam o chuveiro às 19h, a distribuidora precisa de cabos
        e transformadores capazes de aguentar aquele instante — que ficam ociosos no resto
        do tempo. A tarifa mais cara na ponta é um incentivo para espalhar o consumo e
        adiar investimento em infraestrutura.</p>`;
    }

    // ---------- geração distribuída ----------
    if (tarifas && muni) {
      const c = tarifas.modalidades.convencional.unico;
      const t = tarifas.tributos;
      const fioBkwh = c.fio_b * tarifas.fio_b_percentual / 1000 / (1 - t.icms_pr - t.pis_cofins);

      document.getElementById("ent-gd").innerHTML = `
        <p>Quem instala painel solar não guarda a energia: o excedente vai para a rede e
        vira <b>crédito</b>, abatido da conta depois. É o Sistema de Compensação de Energia
        Elétrica (SCEE).</p>

        <p>Até 2022 esse crédito abatia a conta inteira. A <b>Lei 14.300/2022</b> mudou:
        quem injeta passa a pagar o <b>Fio B</b> sobre a energia injetada, porque usou a
        rede para escoá-la. A cobrança sobe 15 pontos por ano:</p>

        <div class="ent-escada">
          ${[2023, 2024, 2025, 2026, 2027, 2028].map((ano) => {
            const pct = { 2023: 15, 2024: 30, 2025: 45, 2026: 60, 2027: 75, 2028: 90 }[ano];
            const atual = ano === tarifas.ano_fio_b;
            return `<div class="${atual ? "atual" : ""}"><b>${pct}%</b><span>${ano}</span></div>`;
          }).join("")}
        </div>

        <p>Em ${tarifas.ano_fio_b} isso equivale a <b>${brl(fioBkwh)} por kWh injetado</b>.
        Note o detalhe que muda tudo: <b>a energia gerada e consumida no mesmo instante não
        paga nada disso</b> — ela nem chega a passar pelo medidor. Por isso o painel de cada
        prosumidor destaca quanto do sol foi “usado na hora”: é a parcela que escapa
        inteiramente da cobrança.</p>

        <p class="ent-nota">Em Foz do Iguaçu há <b>${fmt(muni.ufv_residencial)}</b> casas com
        geração solar, somando <b>${fmt(muni.potencia_residencial_mw, 1)} MW</b> — média de
        ${fmt(muni.potencia_media_residencial_kw, 2)} kW por casa. A adesão saltou a partir de
        2021 e hoje é de ${fmt(muni.taxa_adesao_residencial * 100, 1)}% dos domicílios.</p>`;
    }

    // ---------- dados ----------
    if (consumo && irrad) {
      const res = consumo.por_classe.find((x) => x.classe === "Residencial");
      document.getElementById("ent-dados").innerHTML = `
        <p>Nada aqui é chute. Cada peça vem de uma base pública, e a plataforma marca em
        cada número se ele é <b class="selo selo-real">real</b>,
        <b class="selo selo-estimado">estimado</b> ou
        <b class="selo selo-simulado">simulado</b>.</p>

        <table class="ent-tabela">
          <tr><td><b>IBGE</b> — Censo 2022</td><td>limites dos bairros e população</td></tr>
          <tr><td><b>OpenStreetMap</b></td><td>contorno dos imóveis, ruas e subestações</td></tr>
          <tr><td><b>ANEEL</b> — Geração Distribuída</td><td>quantas casas têm painel solar</td></tr>
          <tr><td><b>ANEEL</b> — SAMP</td><td>consumo médio real: ${fmt(res.kwh_mes_por_uc, 1)} kWh/mês por residência</td></tr>
          <tr><td><b>ANEEL</b> — CTR</td><td>formato das curvas, medido de 15 em 15 minutos</td></tr>
          <tr><td><b>ANEEL</b> — Componentes Tarifárias</td><td>tarifas e Fio B homologados</td></tr>
          <tr><td><b>NASA POWER</b></td><td>irradiância solar local: ${fmt(irrad.estatisticas.hsp_kwh_m2_dia, 2)} kWh/m²/dia</td></tr>
          <tr><td><b>Google Open Buildings</b></td><td>altura das edificações (±1,5 m)</td></tr>
        </table>

        <p class="ent-nota"><b>O que é simulado.</b> O consumo de uma casa específica é
        protegido por LGPD e nenhuma distribuidora o publica. Então a curva de cada imóvel
        é gerada pelo modelo: o <em>formato</em> vem das curvas medidas pela ANEEL, o
        <em>volume</em> da média real por unidade consumidora, e a <em>variação entre
        imóveis</em> da área real de cada telhado. A média do conjunto bate com a medição;
        o valor de uma casa específica não é a medição dela.</p>`;
    }

    carregado = true;
  }

  async function abrir() {
    await montar();
    document.getElementById("entenda-tela").hidden = false;
    document.getElementById("entenda-tela").scrollTop = 0;
  }

  function fechar() {
    document.getElementById("entenda-tela").hidden = true;
  }

  return { abrir, fechar };
})();
