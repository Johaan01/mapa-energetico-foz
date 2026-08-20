/* Tela 2 — painel da unidade consumidora.
   Abre ao clicar num imovel no mapa. Todo numero em R$ sai das tarifas homologadas
   reais da Copel (ANEEL, REH 3.592/2026) aplicadas a curva de 24h daquele imovel. */

const UC = (() => {
  let tarifas = null;

  const brl = (v) =>
    new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
  const num = (v, d = 0) =>
    new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);

  const DIAS_MES = 30.4;

  /* Canvas nítido: o elemento é esticado por CSS até a largura do bloco, então
     desenhar no tamanho nominal deixa tudo borrado em tela retina ou monitor grande.
     Aqui o buffer passa a ter o tamanho real em pixels do dispositivo e o contexto é
     escalado, de modo que o resto do código continua desenhando em coordenadas CSS. */
  function prepararCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const larguraCss = canvas.clientWidth || canvas.width;
    const alturaCss = parseFloat(getComputedStyle(canvas).height) || canvas.height;

    canvas.width = Math.round(larguraCss * dpr);
    canvas.height = Math.round(alturaCss * dpr);

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w: larguraCss, h: alturaCss };
  }
  // Modelo de receita: ficamos com este percentual da economia comprovada.
  const TAXA = 0.20;
  // Custo de disponibilidade: a distribuidora cobra um minimo mesmo se voce nao
  // consumir nada. 30 kWh para ligacao monofasica (Res. 1.000/2021).
  const MINIMO_KWH_MES = 30;

  async function carregarTarifas() {
    if (!tarifas) tarifas = await fetch("data/tarifas.json").then((r) => r.json());
    return tarifas;
  }

  /* Tarifa final em R$/kWh, ja com tributos. Os valores da ANEEL vem em R$/MWh
     sem tributo; ICMS e PIS/COFINS entram "por dentro". */
  function comTributos(rsPorMWh) {
    const t = tarifas.tributos;
    return rsPorMWh / 1000 / (1 - t.icms_pr - t.pis_cofins);
  }

  function postoBranca(hora) {
    const h = tarifas.horarios_branca;
    if (h.ponta.includes(hora)) return "ponta";
    if (h.intermediario.includes(hora)) return "intermediário";
    return "fora_ponta";
  }

  /* Separa a curva em: usado na hora (autoconsumo), injetado e comprado da rede. */
  function decompor(consumo, geracao) {
    const autoconsumo = [], injetado = [], comprado = [];
    for (let h = 0; h < 24; h++) {
      const c = consumo[h] || 0;
      const g = geracao[h] || 0;
      autoconsumo.push(Math.min(c, g));
      injetado.push(Math.max(g - c, 0));
      comprado.push(Math.max(c - g, 0));
    }
    return { autoconsumo, injetado, comprado };
  }

  /* Conta mensal na tarifa convencional.
     Sob o SCEE (Lei 14.300) a energia injetada vira credito que abate o consumo, mas
     o prosumidor paga o Fio B sobre o que injetou — 60% dele em 2026. */
  function contaConvencional({ comprado, injetado }) {
    const t = tarifas.modalidades.convencional.unico;
    const cheia = comTributos(t.te + t.tusd);
    const fioB = comTributos(t.fio_b * tarifas.fio_b_percentual);

    const compradoMes = comprado.reduce((a, b) => a + b, 0) * DIAS_MES;
    const injetadoMes = injetado.reduce((a, b) => a + b, 0) * DIAS_MES;

    const compensado = Math.min(injetadoMes, compradoMes);
    const faturado = Math.max(compradoMes - compensado, MINIMO_KWH_MES);

    return {
      total: faturado * cheia + compensado * fioB,
      custoFioB: compensado * fioB,
      compradoMes,
      injetadoMes,
      compensado,
      tarifaCheia: cheia,
    };
  }

  /* Mesma energia, tarifa branca: o preco muda por hora do dia. */
  function contaBranca({ comprado, injetado }) {
    const b = tarifas.modalidades.branca;
    let total = 0;
    for (let h = 0; h < 24; h++) {
      const p = postoBranca(h);
      const faixa = b[p === "intermediário" ? "intermediário" : p] || b.fora_ponta;
      total += comprado[h] * DIAS_MES * comTributos(faixa.te + faixa.tusd);
    }
    const injetadoMes = injetado.reduce((a, b2) => a + b2, 0) * DIAS_MES;
    const fioB = comTributos(b.fora_ponta.fio_b * tarifas.fio_b_percentual);
    return { total: total + injetadoMes * fioB };
  }

  /* Quanto a conta seria com a MESMA energia, na tarifa de um ano atras.
     Separa o que subiu por reajuste do que mudaria por habito — o contrato do
     produto se apoia justamente nessa comparacao. */
  function contaAnoPassado({ comprado }) {
    const v = tarifas.vigencia_anterior;
    if (!v || !v.te) return null;
    const cheia = comTributos(v.te + v.tusd);
    const compradoMes = comprado.reduce((a, b) => a + b, 0) * DIAS_MES;
    return { total: Math.max(compradoMes, MINIMO_KWH_MES) * cheia, vigencia: v };
  }

  /* Economia possivel deslocando consumo para fora do horario de ponta.
     Assumimos que 35% da carga da ponta e deslocavel (chuveiro, maquina, forno). */
  const FRACAO_DESLOCAVEL = 0.35;

  function economiaDeslocando({ comprado }) {
    const t = tarifas.modalidades.convencional.unico;
    const b = tarifas.modalidades.branca;
    const cheia = comTributos(t.te + t.tusd);
    const foraPonta = comTributos(b.fora_ponta.te + b.fora_ponta.tusd);
    const ponta = comTributos(b.ponta.te + b.ponta.tusd);

    let kwhPonta = 0;
    for (const h of tarifas.horarios_branca.ponta) kwhPonta += (comprado[h] || 0) * DIAS_MES;

    const deslocavel = kwhPonta * FRACAO_DESLOCAVEL;
    // Na branca, o que sair da ponta passa a custar tarifa fora-ponta.
    return { kwhPonta, deslocavel, economia: deslocavel * (ponta - foraPonta), cheia };
  }

  /* ---------- histórico mensal ----------
     O contrato e participativo: ficamos com um percentual da economia. Para isso ser
     auditavel, a variacao da conta precisa ser DECOMPOSTA — parte vem de reajuste
     tarifario, parte de sazonalidade, e so o resto vem de mudanca de habito.

       Δtarifa  = consumo_do_ano_passado x (tarifa_hoje - tarifa_de_entao)
       Δconsumo = (consumo_hoje - consumo_do_ano_passado) x tarifa_hoje

     A taxa incide apenas sobre Δconsumo negativo (economia real de habito). Sem essa
     separacao, cobrariamos por reajuste da ANEEL e por verao mais quente. */

  let sazonalidade = null;

  async function carregarSazonalidade() {
    if (sazonalidade === null) {
      sazonalidade = await fetch("data/sazonalidade.json")
        .then((r) => r.json())
        .catch(() => false);
    }
    return sazonalidade;
  }

  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
                 "jul", "ago", "set", "out", "nov", "dez"];

  // Reducao de consumo atribuida ao serviço. Premissa declarada da demonstração:
  // o cliente passou a deslocar carga depois de usar a plataforma.
  const REDUCAO_PELO_SERVICO = 0.06;

  function historicoMensal(consumoDiaMedio, anoAtual = 2026, anoAnterior = 2025) {
    if (!sazonalidade) return null;

    const idx = sazonalidade.consumo_indice.por_mes;
    const tar = sazonalidade.tarifa_rs_mwh.por_mes;
    const meses = [];

    for (let m = 1; m <= 12; m++) {
      const chaveAtual = `${anoAtual}-${String(m).padStart(2, "0")}`;
      const chaveAnterior = `${anoAnterior}-${String(m).padStart(2, "0")}`;
      const tAtual = tar[chaveAtual], tAnterior = tar[chaveAnterior];
      if (!tAtual || !tAnterior) continue;

      const sazonal = idx[m] ?? idx[String(m)] ?? 1;
      const kwhAntes = consumoDiaMedio * DIAS_MES * sazonal;
      const kwhAgora = kwhAntes * (1 - REDUCAO_PELO_SERVICO);

      const precoAgora = comTributos(tAtual);
      const precoAntes = comTributos(tAnterior);

      const contaAgora = kwhAgora * precoAgora;
      const contaAntes = kwhAntes * precoAntes;

      meses.push({
        mes: MESES[m - 1],
        kwhAntes, kwhAgora,
        contaAntes, contaAgora,
        efeitoTarifa: kwhAntes * (precoAgora - precoAntes),
        efeitoConsumo: (kwhAgora - kwhAntes) * precoAgora,
      });
    }
    return meses;
  }

  function desenharHistorico(canvas, meses) {
    const { ctx, w, h } = prepararCanvas(canvas);
    const base = h - 26, topo = 16;
    ctx.clearRect(0, 0, w, h);
    if (!meses || !meses.length) return;

    const max = Math.max(...meses.flatMap((m) => [m.contaAntes, m.contaAgora]));
    const larg = w / meses.length;
    const alt = (v) => (v / max) * (base - topo);

    // As duas barras do mês encostam uma na outra; o vão fica entre meses. Assim a
    // comparação que importa (este ano x ano passado) é a leitura imediata.
    const bw = larg * 0.40;
    meses.forEach((m, i) => {
      const centro = i * larg + larg / 2;

      ctx.fillStyle = "#c2c7cc";
      ctx.fillRect(centro - bw, base - alt(m.contaAntes), bw, alt(m.contaAntes));
      ctx.fillStyle = "#16324a";
      ctx.fillRect(centro, base - alt(m.contaAgora), bw, alt(m.contaAgora));

      ctx.fillStyle = "#5a6570";
      ctx.font = "10px 'Segoe UI', Arial";
      ctx.textAlign = "center";
      ctx.fillText(m.mes, centro, h - 9);

      // Diferença percentual do mês: é o número que o cliente procura.
      const dif = m.contaAntes > 0 ? (m.contaAgora / m.contaAntes - 1) * 100 : 0;
      ctx.font = "9px 'Segoe UI', Arial";
      ctx.fillStyle = dif > 0 ? "#a32b22" : "#2e7d5b";
      ctx.fillText(`${dif > 0 ? "+" : ""}${dif.toFixed(0)}%`,
                   centro, base - alt(Math.max(m.contaAntes, m.contaAgora)) - 5);
    });

    ctx.strokeStyle = "#ccd1d6";
    ctx.beginPath(); ctx.moveTo(0, base); ctx.lineTo(w, base); ctx.stroke();
  }

  /* Em qual arquétipo este imóvel cai, e portanto quanto ele tem a ganhar.
     Os mesmos indicadores usados em pipeline/perfis_consumidor.py sobre as curvas
     medidas da ANEEL: hora do pico, fator de carga e concentração na ponta. */
  function arquetipo(comprado, ehProsumidor) {
    const total = comprado.reduce((a, b) => a + b, 0) || 1;
    const pico = comprado.indexOf(Math.max(...comprado));
    const fatorCarga = (total / 24) / Math.max(...comprado, 1e-6);
    const pctPonta = tarifas.horarios_branca.ponta
      .reduce((a, h) => a + comprado[h], 0) / total * 100;

    let nome;
    if (fatorCarga >= 0.72) nome = "Constante";
    else if (pico >= 5 && pico <= 9) nome = "Matinal";
    else if (pico >= 10 && pico <= 16) nome = "Diurno";
    else if (pico >= 17 && pico <= 22) nome = "Pico noturno";
    else nome = "Madrugada";

    // A faixa de cobrança segue o que dá para deslocar, não o tamanho da conta:
    // quem já consome fora da ponta tem pouco a ganhar por mais que gaste.
    let faixa, rotuloFaixa;
    if (pctPonta >= 22) { faixa = "alta"; rotuloFaixa = "alto"; }
    else if (pctPonta >= 14) { faixa = "media"; rotuloFaixa = "médio"; }
    else { faixa = "baixa"; rotuloFaixa = "baixo"; }

    return { nome: ehProsumidor ? `${nome} · com geração` : nome,
             faixa, rotuloFaixa, pctPonta, fatorCarga };
  }

  /* ---------- render ---------- */

  function cartao(rotulo, valor, nota, classe = "") {
    return `<div class="uc-card ${classe}">
      <span class="uc-card-rot">${rotulo}</span>
      <span class="uc-card-val">${valor}</span>
      ${nota ? `<span class="uc-card-nota">${nota}</span>` : ""}
    </div>`;
  }

  function barraSol(dec) {
    const soma = (a) => a.reduce((x, y) => x + y, 0);
    const auto = soma(dec.autoconsumo), inj = soma(dec.injetado), comp = soma(dec.comprado);
    const total = auto + inj + comp || 1;
    const pct = (v) => (v / total) * 100;
    return `
      <div class="uc-barra">
        <span style="width:${pct(auto)}%;background:#2e7d5b" title="usou na hora"></span>
        <span style="width:${pct(inj)}%;background:#a32b22" title="injetou na rede"></span>
        <span style="width:${pct(comp)}%;background:#1f6f8b" title="comprou da Copel"></span>
      </div>
      <ul class="uc-barra-leg">
        <li><i style="background:#2e7d5b"></i>usou na hora — ${num(pct(auto))}% (não paga tarifa)</li>
        <li><i style="background:#a32b22"></i>injetou — ${num(pct(inj))}% (volta pagando Fio B)</li>
        <li><i style="background:#1f6f8b"></i>comprou da Copel — ${num(pct(comp))}%</li>
      </ul>`;
  }

  function desenharCurva(canvas, consumo, geracao) {
    const { ctx, w, h } = prepararCanvas(canvas);
    const pad = 22;
    ctx.clearRect(0, 0, w, h);

    const max = Math.max(...consumo, ...geracao, 0.001);
    const x = (i) => pad + (i / 23) * (w - pad - 8);
    const y = (v) => h - pad - (v / max) * (h - pad - 10);

    // faixa de ponta da tarifa branca
    ctx.fillStyle = "rgba(163,43,34,0.10)";
    const p = tarifas.horarios_branca.ponta;
    ctx.fillRect(x(p[0]) - 4, 6, x(p[p.length - 1]) - x(p[0]) + 8, h - pad - 6);

    // eixos
    ctx.strokeStyle = "#ccd1d6";
    ctx.beginPath(); ctx.moveTo(pad, h - pad); ctx.lineTo(w - 8, h - pad); ctx.stroke();

    const linha = (serie, cor, preencher) => {
      ctx.beginPath();
      serie.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
      if (preencher) {
        ctx.lineTo(x(23), h - pad); ctx.lineTo(x(0), h - pad); ctx.closePath();
        ctx.fillStyle = cor + "33"; ctx.fill();
      }
      ctx.strokeStyle = cor; ctx.lineWidth = 1.8; ctx.stroke();
    };

    if (geracao.some((v) => v > 0)) linha(geracao, "#2e7d5b", true);
    linha(consumo, "#16324a", false);

    ctx.fillStyle = "#5a6570";
    ctx.font = "9px 'Segoe UI', Arial";
    for (const hh of [0, 6, 12, 18, 23]) ctx.fillText(`${hh}h`, x(hh) - 5, h - 7);
  }

  /* ---------- entrada ---------- */

  async function abrir(props) {
    await carregarTarifas();
    await carregarSazonalidade();

    const carga = JSON.parse(JSON.stringify(props.carga_kwh || []));
    // Se o bairro ainda nao foi reprocessado, consumo/geracao nao existem: derivamos
    // do liquido (o que da uma leitura conservadora, sem autoconsumo).
    const consumo = props.consumo_kwh || carga.map((v) => Math.max(v, 0));
    const geracao = props.geracao_kwh || carga.map((v) => Math.max(-v, 0));

    const dec = decompor(consumo, geracao);
    const conv = contaConvencional(dec);
    const branca = contaBranca(dec);
    const passado = contaAnoPassado(dec);
    const desloc = economiaDeslocando(dec);

    const ehProsumidor = props.perfil === "prosumidor";
    const consumoMes = consumo.reduce((a, b) => a + b, 0) * DIAS_MES;
    const geracaoMes = geracao.reduce((a, b) => a + b, 0) * DIAS_MES;
    const autoPct = geracaoMes > 0
      ? (dec.autoconsumo.reduce((a, b) => a + b, 0) * DIAS_MES / geracaoMes) * 100 : 0;

    const economia = Math.max(desloc.economia, 0);
    const nossaTaxa = economia * TAXA;

    document.getElementById("uc-titulo").textContent = `Imóvel #${props.building_id}`;
    document.getElementById("uc-sub").textContent =
      `${num(props.area_m2)} m² · ${props.pavimentos} pavimento(s) · transformador #${props.trafo_id}`;

    // Arquétipo e faixa de cobrança em destaque: era a informação que mais importa
    // para o cliente e estava diluída no texto corrido.
    const arq = arquetipo(dec.comprado, ehProsumidor);
    document.getElementById("uc-perfil-tag").innerHTML = `
      <span class="uc-tag-classe">${ehProsumidor ? "Prosumidor" : "Consumidor"}</span>
      <span class="uc-tag-arq">${arq.nome}</span>
      <span class="uc-tag-faixa faixa-${arq.faixa}">potencial ${arq.rotuloFaixa}</span>`;

    const topo = [
      cartao("Conta estimada / mês", brl(conv.total),
             `${num(consumoMes)} kWh consumidos`, "uc-neutro"),
      passado
        ? cartao("No mesmo mês do ano passado", brl(passado.total),
                 `mesma energia, tarifa de ${passado.vigencia.inicio.slice(0, 7)} — ` +
                 `diferença de ${brl(conv.total - passado.total)} vem do reajuste`, "uc-alerta")
        : "",
      cartao("Economia possível / mês", brl(economia),
             `deslocando ${num(desloc.deslocavel, 1)} kWh para fora da ponta`, "uc-bom"),
    ].join("");
    document.getElementById("uc-topo").innerHTML = topo;

    const secundarios = [
      ehProsumidor
        ? cartao("Sol usado na hora", `${num(autoPct)}%`,
                 `${num(geracaoMes)} kWh gerados no mês`)
        : cartao("Geração própria", "—", "imóvel sem geração distribuída"),
      cartao("Fio B pago", brl(conv.custoFioB),
             ehProsumidor
               ? `${num(tarifas.fio_b_percentual * 100)}% em ${tarifas.ano_fio_b} (Lei 14.300)`
               : "só incide sobre energia injetada"),
      cartao("Tarifa convencional", brl(conv.total), "modalidade atual"),
      cartao("Se fosse tarifa branca", brl(branca.total),
             branca.total < conv.total ? "seria mais barata" : "seria mais cara neste perfil"),
    ].join("");
    document.getElementById("uc-secundario").innerHTML = secundarios;

    const melhorBranca = branca.total < conv.total;
    document.getElementById("uc-recado-texto").innerHTML = `
      ${ehProsumidor
        ? `Seu sistema gera ${num(geracaoMes)} kWh/mês, mas só ${num(autoPct)}% é usado na hora —
           o resto vai para a rede e volta pagando Fio B (${brl(conv.custoFioB)}/mês).
           Consumir mais durante o dia, ou guardar em bateria, corta esse custo.`
        : `Você comprou ${num(conv.compradoMes)} kWh da Copel neste mês.
           ${num(desloc.kwhPonta, 1)} kWh caíram no horário de ponta (18h–21h), que é o mais caro.`}
      Deslocando parte disso, a economia estimada é de <strong>${brl(economia)}/mês</strong>.
      ${melhorBranca
        ? "Neste perfil, migrar para tarifa branca compensa."
        : "Neste perfil, a tarifa branca <em>não</em> compensa — o consumo está concentrado na ponta."}
    `;

    document.getElementById("uc-acoes").innerHTML = [
      ehProsumidor
        ? `Programar bateria ou deslocar consumo para 10h–15h: hoje ${num(100 - autoPct)}% da geração vai para a rede.`
        : `Deslocar chuveiro e máquina para depois das 21h evita a ponta.`,
      `Ponta (18h–21h) custa ${brl(comTributos(tarifas.modalidades.branca.ponta.te + tarifas.modalidades.branca.ponta.tusd))}/kWh
       contra ${brl(comTributos(tarifas.modalidades.branca.fora_ponta.te + tarifas.modalidades.branca.fora_ponta.tusd))}/kWh fora dela.`,
      passado
        ? `A tarifa subiu ${num(((tarifas.modalidades.convencional.unico.te + tarifas.modalidades.convencional.unico.tusd) /
            (passado.vigencia.te + passado.vigencia.tusd) - 1) * 100, 1)}% em um ano — parte da conta maior não é consumo, é reajuste.`
        : "",
      `Nosso contrato: ficamos com ${num(TAXA * 100)}% da economia comprovada
       (${brl(nossaTaxa)}/mês), você fica com ${brl(economia - nossaTaxa)}.`,
    ].filter(Boolean).map((t) => `<li>${t}</li>`).join("");

    document.getElementById("uc-barra-sol").innerHTML = barraSol(dec);
    desenharCurva(document.getElementById("uc-curva"), consumo, geracao);

    // Histórico de 12 meses com a decomposição que sustenta o contrato.
    const bloco = document.getElementById("uc-historico");
    const meses = historicoMensal(dec.comprado.reduce((a, b) => a + b, 0));
    if (meses && meses.length) {
      bloco.hidden = false;
      desenharHistorico(document.getElementById("uc-barras-ano"), meses);

      const somar = (campo) => meses.reduce((a, m) => a + m[campo], 0);
      const porTarifa = somar("efeitoTarifa");
      const porHabito = somar("efeitoConsumo");
      const economiaHabito = Math.max(-porHabito, 0);
      const taxa = economiaHabito * TAXA;

      document.getElementById("uc-historico-resumo").innerHTML = `
        <div class="uc-decomp">
          <div><span>Conta subiu por <strong>reajuste da tarifa</strong></span>
               <b class="neg">${brl(porTarifa)}</b>
               <em>não causamos, não cobramos</em></div>
          <div><span>Conta caiu por <strong>mudança de hábito</strong></span>
               <b class="pos">${brl(porHabito)}</b>
               <em>é o efeito do serviço</em></div>
          <div class="uc-decomp-total">
            <span>Economia no ano · nossa taxa (${num(TAXA * 100)}%)</span>
            <b>${brl(economiaHabito)} · ${brl(taxa)}</b>
            <em>você fica com ${brl(economiaHabito - taxa)}</em></div>
        </div>`;
    } else {
      bloco.hidden = true;
    }

    document.getElementById("uc-tela").hidden = false;
  }

  function fechar() {
    document.getElementById("uc-tela").hidden = true;
  }

  return { abrir, fechar };
})();
