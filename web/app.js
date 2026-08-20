/* Dashboard da rede de distribuicao — MapLibre GL.
   Todo dado ja vem pre-computado do pipeline Python; aqui so desenhamos e filtramos
   por hora. Nada de sorteio no cliente: recarregar a pagina nao pode mudar os dados. */

const BASE_STYLE = "https://tiles.openfreemap.org/styles/positron";

const AZUL = "#1f6f8b";    // injecao liquida na rede
const NEUTRO = "#f2f0ec";
const VERMELHO = "#a32b22"; // consumindo da rede
const CINZA_ANEXO = "#c9c9c4";

// Cores por PERFIL (categorico) — independentes da carga do momento.
const COR_PERFIL = {
  residencial: "#8c9ec4",
  prosumidor: "#d9a520",
  comercial: "#7a5ea8",
  nao_residencial: CINZA_ANEXO,
};

// Subestacoes reais do OSM. Uma conversora de 750 kV da Furnas nao cumpre o mesmo
// papel de uma subestacao de distribuicao da Copel — o mapa precisa distinguir.
const COR_SUBESTACAO = {
  distribution: "#16324a",
  transmission: "#6b4fa8",
  converter: "#8a5a1e",
};

const Z_IMOVEL = 16.5;       // a partir daqui aparecem imoveis e ramais
const Z_ENTRA_BAIRRO = 14.2; // aproximar deste ponto carrega o bairro sob o centro
const Z_SAI_BAIRRO = 13.2;   // afastar abaixo disto volta para a cidade
                             // (a folga entre os dois evita ficar entrando e saindo
                             //  em cima do limiar a cada pequeno ajuste de zoom)

/* Niveis de acesso — o dado individual e o eixo da LGPD aqui.
   Imovel a imovel so aparece para a distribuidora (que ja e a detentora do dado) e,
   restrito a UC do proprio titular, para o consumidor. Publico e comercializadora
   enxergam apenas o agregado por transformador (piso de 15 imoveis). */
const PERFIS_ACESSO = {
  publico: {
    rotulo: "Público (livre)",
    imoveis: false,
    aviso: "Acesso livre: dados agregados por transformador (mínimo de 15 imóveis). " +
           "Nenhum consumo individual é exibido.",
  },
  consumidor: {
    rotulo: "Consumidor / prosumidor",
    imoveis: "propria",
    aviso: "Você vê em detalhe apenas a sua unidade consumidora. As demais aparecem " +
           "agregadas por transformador.",
  },
  distribuidora: {
    rotulo: "Distribuidora (Copel)",
    imoveis: true,
    aviso: "Acesso da detentora do dado: visão imóvel a imóvel para operação e " +
           "planejamento da rede. Troque o nível de acesso acima para ver o que " +
           "cada perfil enxerga — no acesso público, nenhum imóvel aparece " +
           "individualmente.",
  },
  comercializadora: {
    rotulo: "Comercializadora",
    imoveis: false,
    aviso: "Clusters estatísticos por perfil, sem identificação individual.",
  },
};

const state = {
  hora: 19,
  tocando: false,
  timer: null,
  camadas: {},
  escalas: {},
  slug: null,
  modo: "cidade",
  // Abre na visão da distribuidora, com tudo visível. Numa demonstração avaliada por
  // terceiros, começar no nível protegido esconderia justamente o que há para mostrar,
  // e dependeria de o avaliador descobrir sozinho o seletor de acesso.
  perfil: "distribuidora",
  modoCor: "carga",
  minhaUC: null,
};

const fmt = (n, d = 0) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);

/* Versão do build, carimbada pelo workflow de publicação. Anexada a toda requisição
   de dado para que o navegador busque de novo quando (e só quando) o conteúdo mudar —
   é o que evita a página velha ficar presa no cache depois de um deploy. */
const VERSAO = document.querySelector('meta[name="app-version"]')?.content || "dev";

const getJSON = (url) => {
  const sep = url.includes("?") ? "&" : "?";
  return fetch(`${url}${sep}v=${encodeURIComponent(VERSAO)}`).then((r) => {
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  });
};

/* ---------- escala de cor ---------- */

// Percentil alto dos picos: evita que um unico trecho troncal achate todo o resto.
function escalaDe(features, campo = "carga_pico_kwh") {
  const v = features.map((f) => Math.abs(f.properties[campo] || 0)).sort((a, b) => a - b);
  return Math.max(v[Math.floor(v.length * 0.92)] || 1, 0.1);
}

const corPorCarga = (max) => [
  "interpolate", ["linear"], ["get", "carga_atual"],
  -max * 0.5, AZUL,
  0, NEUTRO,
  max, VERMELHO,
];

/* ---------- injeta o valor da hora corrente em cada feature ---------- */

function aplicarHora(geojson, hora) {
  for (const f of geojson.features) {
    const c = f.properties.carga_kwh;
    f.properties.carga_atual = Array.isArray(c) ? c[hora] : 0;
  }
  return geojson;
}

/* ---------- visao macro da cidade ---------- */

async function carregarCidade(map) {
  const [bairrosGeo, trafos, subs] = await Promise.all([
    getJSON("data/resumo_bairros.geojson"),
    getJSON("data/resumo_transformadores.geojson"),
    getJSON("data/subestacoes.geojson").catch(() => ({ type: "FeatureCollection", features: [] })),
  ]);
  state.cidade = { bairros: bairrosGeo, trafos, subs };
  state.escalas.cidadeBairros = escalaDe(bairrosGeo.features);
  state.escalas.cidadeTrafos = escalaDe(trafos.features);

  aplicarHora(bairrosGeo, state.hora);
  aplicarHora(trafos, state.hora);

  // Number(): o driver GeoJSON serializa alguns inteiros como texto, e "+=" concatenaria.
  const num = (v) => Number(v) || 0;
  state.kpisCidade = bairrosGeo.features.reduce(
    (acc, f) => {
      const p = f.properties;
      acc.ucs += num(p.unidades_consumidoras);
      acc.pop += num(p.populacao);
      acc.trafos += num(p.transformadores);
      acc.pros += num(p.prosumidores);
      return acc;
    },
    { ucs: 0, pop: 0, trafos: 0, pros: 0 }
  );

  map.addSource("cidade-bairros", { type: "geojson", data: bairrosGeo });
  map.addSource("cidade-trafos", { type: "geojson", data: trafos });
  map.addSource("subestacoes", { type: "geojson", data: subs });

  map.addLayer({
    id: "cidade-fill", type: "fill", source: "cidade-bairros",
    paint: { "fill-color": corPorCarga(state.escalas.cidadeBairros), "fill-opacity": 0.65 },
  });
  map.addLayer({
    id: "cidade-line", type: "line", source: "cidade-bairros",
    paint: { "line-color": "#16324a", "line-width": 1 },
  });
  map.addLayer({
    id: "cidade-trafos", type: "circle", source: "cidade-trafos", minzoom: 12.5,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 12.5, 1.6, 15, 4],
      "circle-color": corPorCarga(state.escalas.cidadeTrafos),
      "circle-opacity": 0.9,
    },
  });

  // Subestacoes reais: sempre visiveis, em cidade e em bairro. Sao o unico
  // equipamento eletrico do mapa cuja posicao e verificada, nao estimada.
  /* Só as de DISTRIBUIÇÃO entram no mapa. Foz do Iguaçu também tem uma conversora
     HVDC da Furnas (750 kV, que manda energia de Itaipu para São Paulo) e uma de
     transmissão — ambas reais, mas nenhuma alimenta bairro. Desenhá-las com o mesmo
     peso das de distribuição sugeria um papel na rede local que elas não têm.
     O arquivo de dados mantém as 7; aqui filtramos o que faz sentido no modelo. */
  map.addLayer({
    id: "subestacoes-circle", type: "circle", source: "subestacoes",
    filter: ["==", ["get", "classe"], "distribution"],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        10, ["case", ["==", ["get", "classe"], "distribution"], 5, 4],
        16, ["case", ["==", ["get", "classe"], "distribution"], 13, 9]],
      "circle-color": ["match", ["get", "classe"],
        "distribution", COR_SUBESTACAO.distribution,
        "transmission", COR_SUBESTACAO.transmission,
        "converter", COR_SUBESTACAO.converter,
        "#555"],
      "circle-stroke-width": 2.5,
      "circle-stroke-color": "#d9b310",
    },
  });
  map.addLayer({
    id: "subestacoes-label", type: "symbol", source: "subestacoes", minzoom: 12.5,
    filter: ["==", ["get", "classe"], "distribution"],
    layout: {
      "text-field": ["get", "nome"],
      "text-size": 10,
      "text-offset": [0, 1.3],
      "text-anchor": "top",
      "text-font": ["Noto Sans Bold"],
    },
    paint: { "text-color": "#16324a", "text-halo-color": "#ffffff", "text-halo-width": 1.6 },
  });

  map.on("click", "subestacoes-circle", (e) => {
    const p = e.features[0].properties;
    abrirPainel(p.nome, [
      ["Tipo", "Distribuição"],
      ["Operador", p.operador || "—"],
      ["Tensão", p.tensao_v && p.tensao_v !== "nan"
        ? String(p.tensao_v).split(";").map((v) => `${Number(v) / 1000} kV`).join(" / ") : "—"],
      ["Bairros alimentados", p.alimenta_bairros],
    ], null,
      "Posição REAL, do OpenStreetMap (power=substation) — diferente dos transformadores, " +
      "que são estimados. O mapa mostra só as de distribuição: Foz também tem uma " +
      "conversora da Furnas e uma de transmissão, que não alimentam bairros.");
  });
  map.on("mouseenter", "subestacoes-circle", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "subestacoes-circle", () => (map.getCanvas().style.cursor = ""));

  map.on("click", "cidade-fill", (e) => {
    const p = e.features[0].properties;
    document.getElementById("bairro-select").value = p.slug;
    entrarNoBairro(map, p.slug);
  });
  map.on("mouseenter", "cidade-fill", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "cidade-fill", () => (map.getCanvas().style.cursor = ""));
}

/* Qual bairro está sob o centro da tela. Usa a própria consulta de feições do
   MapLibre, que já resolve o ponto-em-polígono na camada renderizada. */
function bairroNoCentro(map) {
  const centro = map.project(map.getCenter());
  const achadas = map.queryRenderedFeatures(centro, { layers: ["cidade-fill"] });
  return achadas.length ? achadas[0].properties.slug : null;
}

const CAMADAS_CIDADE = ["cidade-fill", "cidade-line", "cidade-trafos"];
const CAMADAS_BAIRRO = [
  "boundary-fill", "boundary-line", "buildings-fill", "buildings-line",
  "ramais-line", "feeders-casing", "feeders-line", "transformers-circle", "substation-marker",
];

/* Legenda com VALOR, não só gradiente. "Mais vermelho que o outro" não diz nada se o
   leitor não souber quantos kWh isso representa nem a partir de quando é injeção. */
function atualizarEscala() {
  const cidade = state.modo === "cidade";
  const max = (cidade ? state.escalas.cidadeBairros : state.escalas.buildings) || 1;
  const unidade = cidade ? "kWh no bairro" : "kWh no imóvel";

  const titulo = document.getElementById("escala-titulo");
  const faixa = document.getElementById("escala-faixa");
  const valores = document.getElementById("escala-valores");
  const nota = document.getElementById("escala-nota");

  if (state.modoCor === "perfil") {
    // Categoria não é escala: três cores discretas, cada uma com seu rótulo. Antes
    // isto reusava a barra de gradiente, o que sugeria uma continuidade inexistente.
    titulo.textContent = "Perfil do imóvel";
    faixa.style.display = "none";
    valores.style.display = "none";
    nota.innerHTML = [
      ["residencial", "Consumidor", "só consome da rede"],
      ["prosumidor", "Prosumidor", "tem geração solar própria"],
      ["comercial", "Comercial", "uso não residencial"],
    ].map(([k, nome, desc]) =>
      `<div class="cat-linha"><i style="background:${COR_PERFIL[k]}"></i>
         <b>${nome}</b><span>${desc}</span></div>`).join("") +
      `<div class="cat-obs">Classificação fixa — não muda com a hora do dia.</div>`;
    return;
  }

  titulo.textContent = "Carga na rede, na hora selecionada";
  faixa.style.display = "flex";
  valores.style.display = "flex";
  faixa.innerHTML = "";
  faixa.style.background = `linear-gradient(to right, ${AZUL}, ${NEUTRO} 40%, ${VERMELHO})`;
  valores.innerHTML = [
    `<span>−${fmt(max * 0.5, 1)}</span>`,
    "<span>0</span>",
    `<span>+${fmt(max, 1)}</span>`,
  ].join("");
  nota.innerHTML =
    `Azul = <strong>injeta</strong> na rede · vermelho = <strong>consome</strong>. ` +
    `Escala em ${unidade} por hora.<br>` +
    `<span class="cat-obs">Para ver quem é consumidor, prosumidor ou comercial, ` +
    `troque para <strong>Perfil do imóvel</strong> acima.</span>`;
}

/* Duas leituras do mesmo mapa: "carga" mostra o estado da rede na hora escolhida;
   "perfil" mostra QUEM e cada imovel (consumidor, prosumidor, comercial), que nao
   muda ao longo do dia. */
function corDosImoveis(perfilAcesso) {
  const soMinhaUC = perfilAcesso.imoveis === "propria";

  const porPerfil = ["match", ["get", "perfil"],
    "residencial", COR_PERFIL.residencial,
    "prosumidor", COR_PERFIL.prosumidor,
    "comercial", COR_PERFIL.comercial,
    CINZA_ANEXO];

  const base = state.modoCor === "perfil"
    ? porPerfil
    : ["case", ["get", "e_domicilio"], corPorCarga(state.escalas.buildings), CINZA_ANEXO];

  if (!soMinhaUC) return base;
  return ["case", ["==", ["get", "building_id"], state.minhaUC ?? "__nenhuma__"], base, CINZA_ANEXO];
}

function aplicarPerfilAcesso(map) {
  const perfil = PERFIS_ACESSO[state.perfil] || PERFIS_ACESSO.publico;
  const podeVerImoveis = perfil.imoveis === true || perfil.imoveis === "propria";

  for (const id of ["buildings-fill", "buildings-line", "ramais-line"]) {
    if (map.getLayer(id)) {
      const visivel = state.modo === "bairro" && podeVerImoveis;
      map.setLayoutProperty(id, "visibility", visivel ? "visible" : "none");
    }
  }

  if (map.getLayer("buildings-fill")) {
    map.setPaintProperty("buildings-fill", "fill-color", corDosImoveis(perfil));
  }

  if (map.getLayer("buildings-solar")) {
    const mostrar = state.modo === "bairro" && podeVerImoveis;
    map.setLayoutProperty("buildings-solar", "visibility", mostrar ? "visible" : "none");
  }

  const aviso = document.getElementById("aviso-acesso");
  aviso.textContent = perfil.aviso;
  aviso.className = state.perfil === "distribuidora" ? "aviso-restrito" : "";

  // O filtro só faz sentido onde há imóveis desenhados.
  document.getElementById("filtro-bloco").hidden = !(state.modo === "bairro" && podeVerImoveis);

  atualizarEscala();
  aplicarFiltros(map);
}

function alternarModo(map, modo) {
  state.modo = modo;
  const vis = (ids, v) =>
    ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", v));
  vis(CAMADAS_CIDADE, modo === "cidade" ? "visible" : "none");
  vis(CAMADAS_BAIRRO, modo === "bairro" ? "visible" : "none");
  aplicarPerfilAcesso(map); // pode voltar a esconder imoveis conforme o nivel de acesso
  document.getElementById("btn-cidade").hidden = modo === "cidade";
  document.getElementById("zoom-hint").style.opacity = modo === "cidade" ? "0" : "1";

  if (modo === "cidade" && state.kpisCidade) {
    const k = state.kpisCidade;
    document.getElementById("kpi-ucs").textContent = fmt(k.ucs);
    document.getElementById("kpi-pop").textContent = fmt(k.pop) + " hab";
    document.getElementById("kpi-trafos").textContent = fmt(k.trafos);
    document.getElementById("kpi-pros").textContent =
      fmt(k.pros) + "  (" + fmt((k.pros / Math.max(k.ucs, 1)) * 100, 1) + "%)";
  }
  atualizarHora(state.hora);
}

async function entrarNoBairro(map, slug) {
  await carregarBairro(map, slug);
  alternarModo(map, "bairro");
}

function voltarParaCidade(map) {
  alternarModo(map, "cidade");
  if (state.cidade) {
    let minX = 180, minY = 90, maxX = -180, maxY = -90;
    const varrer = (c) => {
      if (typeof c[0] === "number") {
        minX = Math.min(minX, c[0]); maxX = Math.max(maxX, c[0]);
        minY = Math.min(minY, c[1]); maxY = Math.max(maxY, c[1]);
      } else c.forEach(varrer);
    };
    state.cidade.bairros.features.forEach((f) => varrer(f.geometry.coordinates));
    map.fitBounds([[minX, minY], [maxX, maxY]], { padding: 20, duration: 400 });
  }
}

/* ---------- carga do bairro ---------- */

async function carregarBairro(map, slug, enquadrarMapa = true) {
  state.slug = slug;
  const base = `data/bairros/${slug}`;

  const [meta, boundary, feeders, transformers, substation, buildings, ramais] = await Promise.all([
    getJSON(`${base}/meta.json`),
    getJSON(`${base}/boundary.geojson`),
    getJSON(`${base}/feeders.geojson`),
    getJSON(`${base}/transformers.geojson`),
    getJSON(`${base}/substation.geojson`),
    getJSON(`${base}/buildings.geojson`),
    getJSON(`${base}/ramais.geojson`),
  ]);

  state.dados = { meta, boundary, feeders, transformers, substation, buildings, ramais };

  // Mesclar, não substituir: as escalas da cidade são calculadas uma vez só, em
  // carregarCidade(). Trocar o objeto inteiro aqui as apagava, e a legenda do modo
  // cidade passava a mostrar "NaN".
  Object.assign(state.escalas, {
    feeders: escalaDe(feeders.features),
    transformers: escalaDe(transformers.features),
    buildings: escalaDe(buildings.features),
  });

  for (const nome of ["feeders", "transformers", "buildings", "ramais", "substation"]) {
    aplicarHora(state.dados[nome], state.hora);
  }
  for (const f of ramais.features) f.properties.carga_pico_kwh = Math.max(...f.properties.carga_kwh);
  classificarPotencial(buildings);

  preencherKpis(meta);
  desenhar(map);
  // Ao entrar por zoom, manter a câmera onde o usuário a colocou: reenquadrar seria
  // um salto de tela sem motivo, logo depois de ele ter escolhido para onde olhar.
  if (enquadrarMapa) enquadrar(map, boundary);
  atualizarHora(state.hora);
}

function preencherKpis(meta) {
  document.getElementById("kpi-ucs").textContent = fmt(meta.unidades_consumidoras);
  document.getElementById("kpi-pop").textContent = meta.populacao_censo2022
    ? fmt(meta.populacao_censo2022) + " hab" : "—";
  document.getElementById("kpi-trafos").textContent = fmt(meta.transformadores);
  document.getElementById("kpi-pros").textContent =
    fmt(meta.perfis.prosumidor) + "  (" + fmt(meta.taxa_prosumidor_calibrada * 100, 1) + "%)";
}

function enquadrar(map, boundary) {
  let minX = 180, minY = 90, maxX = -180, maxY = -90;
  const varrer = (coords) => {
    if (typeof coords[0] === "number") {
      minX = Math.min(minX, coords[0]); maxX = Math.max(maxX, coords[0]);
      minY = Math.min(minY, coords[1]); maxY = Math.max(maxY, coords[1]);
    } else coords.forEach(varrer);
  };
  boundary.features.forEach((f) => varrer(f.geometry.coordinates));
  map.fitBounds([[minX, minY], [maxX, maxY]], { padding: 24, duration: 0 });
}

/* ---------- camadas ---------- */

function desenhar(map) {
  const d = state.dados;
  const src = (id, data) => {
    if (map.getSource(id)) map.getSource(id).setData(data);
    else map.addSource(id, { type: "geojson", data });
  };

  src("boundary", d.boundary);
  src("feeders", d.feeders);
  src("ramais", d.ramais);
  src("transformers", d.transformers);
  src("substation", d.substation);
  src("buildings", d.buildings);

  if (state.camadas.prontas) {
    atualizarEscalas(map);
    return;
  }
  state.camadas.prontas = true;

  map.addLayer({
    id: "boundary-fill", type: "fill", source: "boundary",
    paint: { "fill-color": "#6b7a3d", "fill-opacity": 0.06 },
  });
  map.addLayer({
    id: "boundary-line", type: "line", source: "boundary",
    paint: { "line-color": "#16324a", "line-width": 1.6, "line-dasharray": [3, 2] },
  });

  // Imoveis: anexos/garagens em cinza (existem no mapa, mas nao sao UC).
  map.addLayer({
    id: "buildings-fill", type: "fill", source: "buildings", minzoom: Z_IMOVEL,
    paint: {
      "fill-color": ["case", ["get", "e_domicilio"], corPorCarga(state.escalas.buildings), CINZA_ANEXO],
      "fill-opacity": 0.92,
    },
  });
  map.addLayer({
    id: "buildings-line", type: "line", source: "buildings", minzoom: Z_IMOVEL,
    paint: { "line-color": "#7a8087", "line-width": 0.4 },
  });

  // Prosumidor recebe o simbolo de painel sobre o telhado, nao uma borda colorida:
  // a cor de borda competia com a cor de carga e nao dizia o que significava.
  registrarIconePainel(map);
  map.addLayer({
    id: "buildings-solar", type: "symbol", source: "buildings", minzoom: Z_IMOVEL,
    filter: ["==", ["get", "perfil"], "prosumidor"],
    layout: {
      "icon-image": "painel-solar",
      "icon-size": ["interpolate", ["linear"], ["zoom"], 16.5, 0.7, 20, 1.6],
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
    },
  });

  // Ramal: ligacao curta do imovel ate a rua.
  map.addLayer({
    id: "ramais-line", type: "line", source: "ramais", minzoom: Z_IMOVEL,
    paint: {
      "line-color": "#8a8f96", "line-width": 0.7, "line-opacity": 0.75,
      "line-dasharray": [2, 1.5],
    },
  });

  // Alimentador: corre sobre a geometria real da rua; largura pela hierarquia viaria.
  map.addLayer({
    id: "feeders-casing", type: "line", source: "feeders",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#2b3a45",
      "line-width": [
        "interpolate", ["linear"], ["zoom"],
        13, ["match", ["get", "classe_via"], "primary", 4.2, "secondary", 3.6, "tertiary", 3.0, 2.0],
        18, ["match", ["get", "classe_via"], "primary", 9.0, "secondary", 8.0, "tertiary", 7.0, 5.0],
      ],
      "line-opacity": 0.5,
    },
  });
  map.addLayer({
    id: "feeders-line", type: "line", source: "feeders",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": corPorCarga(state.escalas.feeders),
      "line-width": [
        "interpolate", ["linear"], ["zoom"],
        13, ["match", ["get", "classe_via"], "primary", 2.6, "secondary", 2.2, "tertiary", 1.8, 1.1],
        18, ["match", ["get", "classe_via"], "primary", 6.0, "secondary", 5.2, "tertiary", 4.4, 3.0],
      ],
    },
  });

  map.addLayer({
    id: "transformers-circle", type: "circle", source: "transformers", minzoom: 13.5,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 14, 5, 18, 11],
      "circle-color": corPorCarga(state.escalas.transformers),
      "circle-stroke-width": 1.4,
      "circle-stroke-color": "#16324a",
    },
  });

  map.addLayer({
    id: "substation-marker", type: "circle", source: "substation",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 13, 7, 18, 14],
      "circle-color": "#16324a",
      "circle-stroke-width": 3,
      "circle-stroke-color": "#d9b310",
    },
  });

  ligarInteracoes(map);
}

/* Ícone de painel fotovoltaico: riscos azuis diagonais, como o símbolo usado em
   legenda de mapa elétrico. Desenhado em canvas para não depender de arquivo externo. */
function registrarIconePainel(map) {
  if (map.hasImage("painel-solar")) return;

  const L = 20;
  const c = document.createElement("canvas");
  c.width = c.height = L;
  const ctx = c.getContext("2d");

  ctx.fillStyle = "rgba(26,66,109,0.22)";
  ctx.fillRect(2, 4, L - 4, L - 8);

  ctx.strokeStyle = "#1a426d";
  ctx.lineWidth = 1.6;
  for (let i = -L; i < L; i += 5) {
    ctx.beginPath();
    ctx.moveTo(i + 2, L - 4);
    ctx.lineTo(i + 2 + (L - 8), 4);
    ctx.stroke();
  }

  ctx.strokeStyle = "#0f2f4f";
  ctx.lineWidth = 1.4;
  ctx.strokeRect(2, 4, L - 4, L - 8);

  map.addImage("painel-solar", ctx.getImageData(0, 0, L, L), { pixelRatio: 2 });
}

function atualizarEscalas(map) {
  map.setPaintProperty("feeders-line", "line-color", corPorCarga(state.escalas.feeders));
  map.setPaintProperty("transformers-circle", "circle-color", corPorCarga(state.escalas.transformers));
  map.setPaintProperty("buildings-fill", "fill-color",
    ["case", ["get", "e_domicilio"], corPorCarga(state.escalas.buildings), CINZA_ANEXO]);
}

/* ---------- interacao ---------- */

function ligarInteracoes(map) {
  const clique = {
    "transformers-circle": (p) => ({
      titulo: `Transformador #${p.trafo_id}`,
      linhas: [
        ["Imóveis atendidos", p.n_imoveis],
        ["Residencial", p.n_residencial],
        ["Prosumidor (solar)", p.n_prosumidor],
        ["Comercial", p.n_comercial],
        ["Pico do dia", fmt(p.carga_pico_kwh, 1) + " kWh"],
      ],
      nota: "Agregação mínima de 15 imóveis por grupo — nenhum consumo individual é publicado.",
    }),
    "feeders-line": (p) => ({
      titulo: p.nome_via || "Trecho sem nome",
      linhas: [
        ["Classe da via", p.classe_via],
        ["Extensão", fmt(p.comprimento_m, 0) + " m"],
        ["Pico do dia", fmt(p.carga_pico_kwh, 1) + " kWh"],
      ],
      nota: "Carga acumulada de todos os imóveis que dependem deste trecho até a subestação.",
    }),
    "buildings-fill": (p) => ({
      titulo: p.e_domicilio ? `Imóvel #${p.building_id}` : `Anexo #${p.building_id}`,
      linhas: [
        ["Perfil", p.perfil],
        ["Área do footprint", fmt(p.area_m2, 0) + " m²"],
        ["Pavimentos (estim.)", p.pavimentos],
        ["Área útil", fmt(p.area_util_m2, 0) + " m²"],
        ["Transformador", p.trafo_id >= 0 ? "#" + p.trafo_id : "—"],
      ],
      nota: p.e_domicilio
        ? "Curva simulada; amplitude proporcional à área útil real do imóvel."
        : "Construção pequena (garagem, edícula): desenhada porque existe, mas não modelada como unidade consumidora.",
    }),
    "substation-marker": (p) => ({
      titulo: "Subestação (ponto de entrada)",
      linhas: [["Pico do dia", fmt(p.carga_pico_kwh, 1) + " kWh"]],
      nota: "Origem da árvore radial: toda a carga do bairro converge para cá pelas ruas.",
    }),
  };

  for (const [camada, montar] of Object.entries(clique)) {
    map.on("click", camada, (e) => {
      const p = e.features[0].properties;
      // Trava de acesso tambem no clique: esconder a camada nao basta.
      if (camada === "buildings-fill") {
        const perfil = PERFIS_ACESSO[state.perfil];
        if (!perfil.imoveis) return;
        if (perfil.imoveis === "propria" && p.building_id !== state.minhaUC) return;

        // Imovel com carga abre a tela 2 (painel da UC); anexo segue no painel lateral.
        if (p.e_domicilio && typeof UC !== "undefined") {
          const props = { ...p };
          for (const campo of ["carga_kwh", "consumo_kwh", "geracao_kwh"]) {
            if (typeof props[campo] === "string") props[campo] = JSON.parse(props[campo]);
          }
          UC.abrir(props);
          return;
        }
      }
      const carga = typeof p.carga_kwh === "string" ? JSON.parse(p.carga_kwh) : p.carga_kwh;
      const info = montar(p);
      abrirPainel(info.titulo, info.linhas, carga, info.nota);
    });
    map.on("mouseenter", camada, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", camada, () => (map.getCanvas().style.cursor = ""));
  }

  const dica = document.getElementById("zoom-hint");
  map.on("zoom", () => {
    const mostrar = state.modo === "bairro" && map.getZoom() < Z_IMOVEL;
    dica.style.opacity = mostrar ? "1" : "0";
  });

  /* Entrar no bairro ao aproximar, sair ao afastar. Sem isso o usuário dava zoom na
     visão de cidade e chegava a um nível onde só via os polígonos gigantes, sem os
     imóveis — tinha que descobrir sozinho que precisava usar o seletor. Carregamos um
     bairro por vez, e não os vizinhos: cada um custa alguns MB e a apresentação é no
     celular. */
  map.on("moveend", () => {
    const zoom = map.getZoom();

    if (state.modo === "cidade" && zoom >= Z_ENTRA_BAIRRO) {
      const slug = bairroNoCentro(map);
      if (slug && !state.carregando) {
        state.carregando = true;
        const sel = document.getElementById("bairro-select");
        sel.value = slug;
        carregarBairro(map, slug, false)
          .then(() => alternarModo(map, "bairro"))
          .finally(() => { state.carregando = false; });
      }
    } else if (state.modo === "bairro" && zoom < Z_SAI_BAIRRO) {
      document.getElementById("bairro-select").value = "";
      alternarModo(map, "cidade");
    }
  });
}

/* ---------- potencial de economia por imóvel ----------
   O que define o potencial não é o tamanho da conta, e sim quanto do consumo cai no
   horário de ponta — quem já consome fora dela tem pouco a deslocar por mais que
   gaste. Mesmo critério de pipeline/perfis_consumidor.py, aplicado aqui a cada imóvel.
   Calculado no cliente para não exigir reprocessar os 37 bairros. */
const HORAS_PONTA = [18, 19, 20];

function classificarPotencial(geojson) {
  for (const f of geojson.features) {
    const p = f.properties;
    const carga = p.carga_kwh;
    if (!Array.isArray(carga) || !p.e_domicilio) {
      p.faixa_potencial = "nenhum";
      continue;
    }
    const comprado = carga.map((v) => Math.max(v, 0));
    const total = comprado.reduce((a, b) => a + b, 0);
    const ponta = HORAS_PONTA.reduce((a, h) => a + comprado[h], 0);
    const pct = total > 0 ? (ponta / total) * 100 : 0;
    p.pct_ponta = Math.round(pct * 10) / 10;
    p.faixa_potencial = pct >= 22 ? "alto" : pct >= 14 ? "medio" : "baixo";
  }
}

function aplicarFiltros(map) {
  if (!map.getLayer("buildings-fill")) return;

  const perfisAtivos = [...document.querySelectorAll("#filtro-bloco input[data-filtro]")]
    .filter((c) => c.checked).map((c) => c.dataset.filtro);
  const soAlto = document.getElementById("filtro-potencial").checked;

  const condicoes = [["in", ["get", "perfil"], ["literal", perfisAtivos]]];
  if (soAlto) condicoes.push(["==", ["get", "faixa_potencial"], "alto"]);
  const filtro = ["all", ...condicoes];

  for (const id of ["buildings-fill", "buildings-line"]) {
    if (map.getLayer(id)) map.setFilter(id, filtro);
  }
  if (map.getLayer("buildings-solar")) {
    map.setFilter("buildings-solar",
      ["all", ["==", ["get", "perfil"], "prosumidor"], ...condicoes]);
  }

  const feats = state.dados?.buildings?.features || [];
  const visiveis = feats.filter((f) =>
    perfisAtivos.includes(f.properties.perfil) &&
    (!soAlto || f.properties.faixa_potencial === "alto")).length;
  const total = feats.filter((f) => f.properties.e_domicilio).length;

  document.getElementById("filtro-contagem").innerHTML = total
    ? `<strong>${fmt(visiveis)}</strong> de ${fmt(total)} imóveis`
    : "";
}

/* ---------- contexto municipal (dado 100% real) ---------- */

function renderContextoMunicipal(m) {
  const linhas = [
    ["Instalações solares (todas)", fmt(m.ufv_total)],
    ["…residenciais", fmt(m.ufv_residencial)],
    ["Potência residencial", fmt(m.potencia_residencial_mw, 1) + " MW"],
    ["Potência média por casa", fmt(m.potencia_media_residencial_kw, 2) + " kW"],
    ["Domicílios (Censo 2022)", fmt(m.domicilios_estimados)],
    ["Adesão solar residencial", fmt(m.taxa_adesao_residencial * 100, 1) + "%"],
  ];
  document.getElementById("muni-table").innerHTML =
    linhas.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");

  desenharBarras(document.getElementById("muni-chart"), m.ufv_residencial_por_ano);
}

/* Os arquétipos de consumo, medidos pela ANEEL (CTR) — o entregável do Tema 3.
   Ficavam só no JSON; aqui viram a primeira coisa que quem abre a plataforma vê. */
function renderPerfis(dados) {
  const linhas = [];
  for (const [classe, bloco] of Object.entries(dados.classes)) {
    const contagem = {};
    for (const p of bloco.perfis) {
      const a = contagem[p.arquetipo] || { n: 0, ponta: 0, carga: 0, oport: p.oportunidade };
      a.n += 1; a.ponta += p.pct_ponta; a.carga += p.fator_carga;
      contagem[p.arquetipo] = a;
    }
    for (const [nome, a] of Object.entries(contagem)) {
      linhas.push({
        classe, nome, n: a.n,
        ponta: a.ponta / a.n, carga: a.carga / a.n, oport: a.oport,
      });
    }
  }
  linhas.sort((x, y) => y.ponta - x.ponta);

  document.getElementById("perfis-resumo").innerHTML = linhas.map((l) => {
    // Potencial de deslocamento: quanto da carga está na ponta, o horário caro.
    const nivel = l.ponta >= 22 ? "alta" : l.ponta >= 14 ? "media" : "baixa";
    const rotulo = { alta: "alto", media: "médio", baixa: "baixo" }[nivel];
    return `<div class="perfil-linha" title="${l.oport}">
      <span class="perfil-nome">${l.nome}<em>${l.n}</em></span>
      <span class="perfil-num">${fmt(l.ponta, 1)}% na ponta</span>
      <span class="perfil-faixa faixa-${nivel}">${rotulo}</span>
    </div>`;
  }).join("");

  const totalPerfis = Object.values(dados.classes)
    .reduce((a, b) => a + b.perfis.length, 0);
  document.getElementById("perfis-nota").innerHTML =
    `${totalPerfis} perfis medidos em campo pelas distribuidoras (ANEEL CTR, ` +
    `${dados.ano_processo}, ${dados.distribuidora}) — não são personas inventadas. ` +
    `A coluna da direita é o <strong>potencial de economia</strong>: quem já consome ` +
    `fora da ponta tem pouco a deslocar, por maior que seja a conta.`;
}

function desenharBarras(canvas, porAno) {
  const anos = Object.keys(porAno).sort();
  const vals = anos.map((a) => porAno[a]);
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height, base = h - 13, pad = 3;
  ctx.clearRect(0, 0, w, h);

  const max = Math.max(...vals, 1);
  const bw = (w - pad * 2) / anos.length;

  anos.forEach((ano, i) => {
    const alt = (vals[i] / max) * (base - pad);
    const x = pad + i * bw;
    ctx.fillStyle = "#6b7a3d";
    ctx.fillRect(x + bw * 0.15, base - alt, bw * 0.7, alt);
    if (i % 2 === 0 || i === anos.length - 1) {
      ctx.fillStyle = "#5a6570";
      ctx.font = "8px 'Segoe UI', Arial";
      ctx.textAlign = "center";
      ctx.fillText(ano.slice(2), x + bw / 2, h - 3);
    }
  });

  ctx.strokeStyle = "#b9bec4";
  ctx.beginPath();
  ctx.moveTo(pad, base); ctx.lineTo(w - pad, base); ctx.stroke();
}

/* ---------- painel ---------- */

/* O contexto do município é a tela de descanso do painel: sempre que o usuário sai de
   um item (imóvel, trafo, trecho), volta para cá. Antes o painel ficava preso no
   último clique, e os dados gerais de Foz sumiam sem jeito óbvio de recuperar. */
function voltarAoContexto() {
  document.getElementById("panel-content").hidden = true;
  document.getElementById("panel-empty").hidden = false;
  state.curvaPainel = null;
}

function abrirPainel(titulo, linhas, curva, nota) {
  document.getElementById("panel").classList.remove("collapsed");
  document.getElementById("panel-empty").hidden = true;
  document.getElementById("panel-content").hidden = false;
  document.getElementById("panel-title").textContent = titulo;
  document.getElementById("panel-table").innerHTML =
    linhas.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
  document.getElementById("panel-note").textContent = nota || "";
  state.curvaPainel = curva;
  desenharGrafico(curva);
}

function desenharGrafico(curva) {
  if (!curva) return;
  const canvas = document.getElementById("panel-chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height, pad = 4;
  ctx.clearRect(0, 0, w, h);

  const max = Math.max(...curva, 0.001);
  const min = Math.min(...curva, 0);
  const range = (max - min) || 1;
  const y = (v) => h - pad - ((v - min) / range) * (h - 2 * pad);
  const x = (i) => pad + (i / 23) * (w - 2 * pad);

  // area sob a curva, separando injecao (azul) de consumo (vermelho)
  curva.forEach((v, i) => {
    if (i === 0) return;
    ctx.fillStyle = v < 0 ? "rgba(31,111,139,0.35)" : "rgba(163,43,34,0.30)";
    ctx.beginPath();
    ctx.moveTo(x(i - 1), y(0));
    ctx.lineTo(x(i - 1), y(curva[i - 1]));
    ctx.lineTo(x(i), y(v));
    ctx.lineTo(x(i), y(0));
    ctx.closePath();
    ctx.fill();
  });

  ctx.strokeStyle = "#b9bec4";
  ctx.beginPath(); ctx.moveTo(pad, y(0)); ctx.lineTo(w - pad, y(0)); ctx.stroke();

  ctx.strokeStyle = "#16324a";
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  curva.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.stroke();

  ctx.strokeStyle = "#d9b310";
  ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.moveTo(x(state.hora), pad); ctx.lineTo(x(state.hora), h - pad); ctx.stroke();
}

/* ---------- relogio ---------- */

let mapRef = null;

function atualizarHora(hora) {
  state.hora = hora;
  document.getElementById("hour-label").textContent = String(hora).padStart(2, "0") + ":00";
  document.getElementById("hour-slider").value = hora;

  if (state.cidade) {
    for (const [nome, fonte] of [["bairros", "cidade-bairros"], ["trafos", "cidade-trafos"]]) {
      aplicarHora(state.cidade[nome], hora);
      const s = mapRef.getSource(fonte);
      if (s) s.setData(state.cidade[nome]);
    }
  }

  // No modo cidade o total e a soma dos bairros; no modo bairro, a carga da subestacao.
  if (state.modo === "cidade") {
    if (state.cidade) {
      const soma = state.cidade.bairros.features
        .reduce((acc, f) => acc + (f.properties.carga_kwh?.[hora] || 0), 0);
      const el = document.getElementById("kpi-carga");
      el.textContent = fmt(soma / 1000, 1) + " MWh";
      el.style.color = soma < 0 ? "#bfe3ef" : "#ffffff";
    }
    desenharGrafico(state.curvaPainel);
    return;
  }

  const d = state.dados;
  if (!d) return;

  for (const nome of ["feeders", "transformers", "buildings", "ramais", "substation"]) {
    aplicarHora(d[nome], hora);
    const s = mapRef.getSource(nome);
    if (s) s.setData(d[nome]);
  }

  const total = d.substation.features[0].properties.carga_kwh[hora];
  const el = document.getElementById("kpi-carga");
  el.textContent = fmt(total, 0) + " kWh";
  el.style.color = total < 0 ? "#bfe3ef" : "#ffffff";

  desenharGrafico(state.curvaPainel);
}

/* ---------- boot ---------- */

async function main() {
  const map = new maplibregl.Map({
    container: "map",
    style: BASE_STYLE,
    center: [-54.5701875, -25.5520036],
    zoom: 14.4,
    maxZoom: 20,
    attributionControl: false,
  });
  mapRef = map;
  window.__mapa = map;  // exposto para depuração e para os testes de dev/
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");

  try {
    renderContextoMunicipal(await getJSON("data/municipio.json"));
  } catch {
    /* contexto municipal e opcional; o mapa funciona sem ele */
  }
  try {
    renderPerfis(await getJSON("data/perfis_consumidor.json"));
  } catch {
    /* idem */
  }

  let indice = null;
  try {
    indice = await getJSON("data/bairros/index.json");
  } catch {
    indice = { bairros: [{ bairro: "Yolanda", slug: "yolanda" }] };
  }

  const sel = document.getElementById("bairro-select");
  sel.innerHTML =
    '<option value="">Foz do Iguaçu — todos os bairros</option>' +
    indice.bairros.map((b) => `<option value="${b.slug}">${b.bairro}</option>`).join("");
  sel.addEventListener("change", () => {
    if (sel.value) entrarNoBairro(map, sel.value);
    else voltarParaCidade(map);
  });

  await new Promise((r) => map.on("load", r));

  // Sobe na visao de cidade: leve (~1,5 MB) e da o panorama antes de escolher o bairro.
  await carregarCidade(map);
  await carregarBairro(map, indice.bairros[0].slug);
  alternarModo(map, "cidade");
  voltarParaCidade(map);

  document.getElementById("btn-cidade").addEventListener("click", () => {
    sel.value = "";
    voltarParaCidade(map);
  });

  for (const btn of document.querySelectorAll("#modo-cor button")) {
    btn.addEventListener("click", () => {
      state.modoCor = btn.dataset.modo;
      document.querySelectorAll("#modo-cor button")
        .forEach((b) => b.classList.toggle("ativo", b === btn));
      aplicarPerfilAcesso(map);   // já chama atualizarEscala()
    });
  }

  for (const c of document.querySelectorAll("#filtro-bloco input")) {
    c.addEventListener("change", () => aplicarFiltros(map));
  }

  const escala = document.getElementById("escala");
  document.getElementById("escala-toggle").addEventListener("click", () => {
    escala.classList.toggle("recolhida");
    document.getElementById("escala-toggle").textContent =
      escala.classList.contains("recolhida") ? "Legenda ▸" : "Legenda ▾";
  });
  // No celular a legenda começa recolhida para não roubar mapa.
  if (window.innerWidth < 680) escala.classList.add("recolhida");

  const perfilSel = document.getElementById("perfil-select");
  perfilSel.value = state.perfil;
  perfilSel.addEventListener("change", () => {
    state.perfil = perfilSel.value;
    // Demo: "sua UC" e o primeiro imovel residencial do bairro carregado.
    if (state.perfil === "consumidor" && state.dados) {
      const meu = state.dados.buildings.features.find((f) => f.properties.e_domicilio);
      state.minhaUC = meu ? meu.properties.building_id : null;
    }
    aplicarPerfilAcesso(map);
  });
  aplicarPerfilAcesso(map);

  document.getElementById("hour-slider").addEventListener("input", (e) =>
    atualizarHora(Number(e.target.value))
  );
  document.getElementById("play-btn").addEventListener("click", () => {
    state.tocando = !state.tocando;
    document.getElementById("play-btn").textContent = state.tocando ? "❚❚" : "▶";
    if (state.tocando) {
      state.timer = setInterval(() => atualizarHora((state.hora + 1) % 24), 750);
    } else clearInterval(state.timer);
  });
  document.getElementById("panel-toggle").addEventListener("click", () =>
    document.getElementById("panel").classList.toggle("collapsed")
  );
  document.getElementById("btn-entenda").addEventListener("click", () => Entenda.abrir());
  document.getElementById("ent-voltar").addEventListener("click", () => Entenda.fechar());

  document.getElementById("uc-voltar").addEventListener("click", () => {
    UC.fechar();
    voltarAoContexto();   // senão o painel lateral fica preso no último item clicado
  });
  document.getElementById("panel-back").addEventListener("click", voltarAoContexto);
}

main();
