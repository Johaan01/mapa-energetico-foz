"""Confere se as curvas geradas batem com o consumo real da ANEEL (SAMP)."""
import geopandas as gpd

import simulate

g = gpd.read_file(r"C:\Users\joao~\hackathon-transicao-energetica\web\data\bairros\yolanda\buildings.geojson")
perfis, curvas, _consumo, _geracao = simulate.simular(g, seed=42)

print(f"{'perfil':12s} {'n':>6s} {'kWh/dia':>9s} {'alvo':>7s} {'kWh/mes':>9s}")
for p in ("residencial", "comercial"):
    m = perfis == p
    d = curvas[m].sum(1).mean()
    print(f"{p:12s} {m.sum():6d} {d:9.2f} {simulate.CONSUMO_MEDIO_KWH_DIA[p]:7.2f} {d * 30.4:9.0f}")

import numpy as np

m = perfis == "prosumidor"
c = curvas[m]
exportado = float(-np.minimum(c, 0.0).sum(axis=1).mean())
puxado = float(np.maximum(c, 0.0).sum(axis=1).mean())
print(f"{'prosumidor':12s} {m.sum():6d} {c.sum(1).mean():9.2f} {'':7s}  (liquido diario)")
print(f"   exportado/dia : {exportado:.2f} kWh  (alvo ANEEL {simulate.INJECAO_MEDIA_KWH_DIA})")
print(f"   puxado/dia    : {puxado:.2f} kWh")
print(f"\npico medio de injecao as 12h: {curvas[m][:, 12].mean():.2f} kWh/h por prosumidor")
print(f"pico medio de consumo as 19h: {curvas[perfis == 'residencial'][:, 19].mean():.2f} kWh/h por residencia")
