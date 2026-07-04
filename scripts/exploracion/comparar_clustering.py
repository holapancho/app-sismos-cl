"""
Paso 1 de la exploracion de clustering para el proyecto de sismos de Chile.

Objetivo: comparar KMeans vs DBSCAN "de fabrica" (parametros por defecto/razonables)
sobre datos reales de USGS, para decidir que algoritmo usar en el pipeline final
(scripts/actualizar_historico.py).

Que se encontro al correr esto:
- KMeans (k=6) reparte los sismos en 6 zonas de tamano MUY desigual (167 a 3328
  puntos) porque fuerza un numero fijo de clusters sobre una franja larga y
  angosta (la fosa de subduccion). Los cortes entre zonas son arbitrarios, no
  reflejan quiebres reales en la actividad sismica.
- DBSCAN (eps=0.15, min_samples=8) sufre "efecto cadena": 97.4% de los sismos
  (10394 de 10673) terminan en un solo cluster gigante, porque la sismicidad es
  densa y continua a lo largo de toda la costa. Un eps global asi no sirve para
  encontrar "zonas" separadas.

Conclusion: ninguno de los dos sirve con estos parametros. Ver
explorar_clustering_v2.py para el siguiente paso (barrido de eps + KDE) y
hdbscan_exploracion.py para la solucion final adoptada (HDBSCAN).
"""

import requests
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler

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
    })

df = pd.DataFrame(rows).dropna(subset=["lat", "lon", "mag"])
print(f"Total de sismos descargados (mag>=4.0, 2015-2026): {len(df)}")
print(df[["lat", "lon", "depth", "mag"]].describe())

# --- KMeans ---
X = df[["lat", "lon"]].values
k = 6
kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
df["kmeans_cluster"] = kmeans.fit_predict(X)

print(f"\n=== KMeans (k={k}) ===")
print(df["kmeans_cluster"].value_counts().sort_index())
print("Centroides (lat, lon):")
for i, c in enumerate(kmeans.cluster_centers_):
    print(f"  cluster {i}: lat={c[0]:.2f}, lon={c[1]:.2f}")

# --- DBSCAN ---
# eps en grados: ~0.5 grados ~ 55 km aprox en latitud
scaler = StandardScaler()
Xs = scaler.fit_transform(X)
dbscan = DBSCAN(eps=0.15, min_samples=8)
df["dbscan_cluster"] = dbscan.fit_predict(Xs)

print(f"\n=== DBSCAN (eps=0.15 escalado, min_samples=8) ===")
n_clusters = len(set(df["dbscan_cluster"])) - (1 if -1 in df["dbscan_cluster"].values else 0)
n_noise = (df["dbscan_cluster"] == -1).sum()
print(f"Clusters encontrados: {n_clusters}")
print(f"Puntos clasificados como ruido (outliers): {n_noise} de {len(df)} ({100*n_noise/len(df):.1f}%)")
print(df["dbscan_cluster"].value_counts().sort_index())

# Comparacion de forma: cuan alargados son los clusters en latitud vs longitud
print("\n=== Dispersion por cluster (lat_std, lon_std) ===")
print("KMeans:")
for c in sorted(df["kmeans_cluster"].unique()):
    sub = df[df["kmeans_cluster"] == c]
    print(f"  cluster {c}: n={len(sub):3d}  lat_std={sub['lat'].std():.2f}  lon_std={sub['lon'].std():.2f}")

print("DBSCAN:")
for c in sorted(df["dbscan_cluster"].unique()):
    sub = df[df["dbscan_cluster"] == c]
    label = "ruido" if c == -1 else str(c)
    print(f"  cluster {label}: n={len(sub):3d}  lat_std={sub['lat'].std():.2f}  lon_std={sub['lon'].std():.2f}")

df.to_csv("comparacion_clustering.csv", index=False)
print("\nGuardado: comparacion_clustering.csv")
