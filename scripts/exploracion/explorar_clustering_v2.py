"""
Paso 2 de la exploracion de clustering: dado que comparar_clustering.py mostro
que DBSCAN con eps=0.15 encadena casi todo en un cluster gigante, este script
prueba si bajar eps rompe esa cadena, y explora una alternativa (densidad/KDE)
en paralelo. Tambien es donde se empieza a guardar la fecha de cada sismo, para
dejar la puerta abierta a features temporales (deteccion de replicas, etc.).

Que se encontro:
- Barrido de eps: el cluster gigante domina hasta eps~0.08-0.10 (51-95% de los
  datos en un solo grupo). Recien en eps=0.04-0.05 se fragmenta en decenas de
  zonas razonables, a costa de mas ruido (~19-25%).
- KDE (densidad continua, sin fronteras discretas) encuentra su hotspot
  principal en lat=-24.11, lon=-67.02 (zona Puna/Atacama, cerca de la frontera
  con Argentina/Bolivia) - esto sirvio despues como validacion cruzada contra
  los clusters de HDBSCAN, que aterrizan en la misma zona de forma independiente.
- Temporalidad: 16.7% de los sismos ocurren a menos de 1 hora del anterior
  (1785 de 10673) - evidencia de secuencias de replicas (ley de Omori), no
  ruido aleatorio. Sugiere que un feature futuro razonable NO es "predecir el
  proximo sismo" (fuera de alcance para un proyecto de portafolio) sino algo
  mas modesto y honesto: marcar sismos que probablemente sean replicas de uno
  anterior, o un indice de "actividad reciente" por zona.

Siguiente paso: afinar_eps.py intenta encontrar el eps optimo de forma
automatica (metodo del codo) en vez de a ojo.
"""

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KernelDensity

URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
params = {
    "format": "geojson",
    "starttime": "2015-01-01",
    "endtime": "2026-07-04",
    "minlatitude": -56,
    "maxlatitude": -17,
    "minlongitude": -76,
    "maxlongitude": -66,
    "minmagnitude": 4.0,
}

print("Descargando datos de USGS...")
resp = requests.get(URL, params=params, timeout=60)
resp.raise_for_status()
data = resp.json()

rows = []
for f in data["features"]:
    lon, lat, depth = f["geometry"]["coordinates"]
    rows.append({
        "lat": lat,
        "lon": lon,
        "depth": depth,
        "mag": f["properties"]["mag"],
        "place": f["properties"]["place"],
        "time_ms": f["properties"]["time"],
    })

df = pd.DataFrame(rows).dropna(subset=["lat", "lon", "mag"])
df["fecha"] = pd.to_datetime(df["time_ms"], unit="ms")
df = df.sort_values("fecha").reset_index(drop=True)
print(f"Total de sismos: {len(df)}  |  rango de fechas: {df['fecha'].min()} a {df['fecha'].max()}")

X = df[["lat", "lon"]].values
scaler = StandardScaler()
Xs = scaler.fit_transform(X)

# --- 1. Barrido de eps en DBSCAN para ver donde se rompe el efecto cadena ---
print("\n=== Barrido de eps (min_samples=8) ===")
print(f"{'eps':>6} | {'n_clusters':>10} | {'cluster mas grande':>18} | {'% en ese cluster':>16} | {'% ruido':>8}")
for eps in [0.15, 0.10, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02]:
    db = DBSCAN(eps=eps, min_samples=8).fit(Xs)
    labels = db.labels_
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    if n_clusters > 0:
        sizes = pd.Series(labels[labels != -1]).value_counts()
        biggest = sizes.max()
    else:
        biggest = 0
    print(f"{eps:6.2f} | {n_clusters:10d} | {biggest:18d} | {100*biggest/len(df):15.1f}% | {100*n_noise/len(df):7.1f}%")

# --- 2. Elegir un eps donde ya no domine un cluster gigante y mirar el detalle ---
EPS_ELEGIDO = 0.04  # ajustar segun lo que muestre el barrido de arriba
db = DBSCAN(eps=EPS_ELEGIDO, min_samples=8).fit(Xs)
df["dbscan_cluster"] = db.labels_
print(f"\n=== Detalle con eps={EPS_ELEGIDO} ===")
resumen = df[df["dbscan_cluster"] != -1].groupby("dbscan_cluster").agg(
    n=("mag", "size"),
    lat_centro=("lat", "mean"),
    lon_centro=("lon", "mean"),
    mag_media=("mag", "mean"),
).sort_values("n", ascending=False)
print(resumen.head(15))
print(f"Ruido: {(df['dbscan_cluster'] == -1).sum()} sismos ({100*(df['dbscan_cluster'] == -1).mean():.1f}%)")

# --- 3. Enfoque alternativo: densidad (KDE) en vez de clusters discretos ---
print("\n=== KDE: mapa de densidad ===")
kde = KernelDensity(bandwidth=0.3, metric="euclidean", kernel="gaussian")
kde.fit(X)  # en grados lat/lon directamente, sin escalar, para graficar facil

lat_grid = np.linspace(df["lat"].min(), df["lat"].max(), 150)
lon_grid = np.linspace(df["lon"].min(), df["lon"].max(), 60)
LON, LAT = np.meshgrid(lon_grid, lat_grid)
grid_points = np.column_stack([LAT.ravel(), LON.ravel()])
log_dens = kde.score_samples(grid_points).reshape(LAT.shape)
dens = np.exp(log_dens)

# top 5 celdas de mayor densidad -> "hotspots"
flat_idx = np.argsort(dens.ravel())[::-1][:5]
print("Top 5 zonas de mayor densidad segun KDE:")
for idx in flat_idx:
    i, j = np.unravel_index(idx, dens.shape)
    print(f"  lat={LAT[i,j]:.2f}, lon={LON[i,j]:.2f}, densidad relativa={dens[i,j]:.4f}")

plt.figure(figsize=(6, 10))
plt.pcolormesh(LON, LAT, dens, shading="auto", cmap="hot")
plt.scatter(df["lon"], df["lat"], s=2, c="cyan", alpha=0.3)
plt.colorbar(label="densidad estimada (KDE)")
plt.title("Densidad de sismos (KDE) - mag>=4.0, 2015-2026")
plt.xlabel("Longitud")
plt.ylabel("Latitud")
plt.tight_layout()
plt.savefig("kde_heatmap.png", dpi=120)
plt.show()
print("Guardado: kde_heatmap.png")

# --- 4. Vistazo a temporalidad (para features futuros de prediccion) ---
print("\n=== Temporalidad ===")
por_anio = df.groupby(df["fecha"].dt.year).size()
print("Sismos por anio:")
print(por_anio)

df["dias_desde_anterior"] = df["fecha"].diff().dt.total_seconds() / 86400
print(f"\nTiempo entre sismos consecutivos (dias): mediana={df['dias_desde_anterior'].median():.2f}, "
      f"min={df['dias_desde_anterior'].min():.4f}, max={df['dias_desde_anterior'].max():.1f}")
print("Sismos con menos de 1 hora de diferencia con el anterior (posibles replicas):",
      (df["dias_desde_anterior"] < (1/24)).sum())

df.to_csv("sismos_con_fecha.csv", index=False)
print("\nGuardado: sismos_con_fecha.csv (incluye columna 'fecha' para analisis temporal futuro)")
