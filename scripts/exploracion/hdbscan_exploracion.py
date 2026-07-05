"""
Paso 4 (final) de la exploracion de clustering: HDBSCAN.

Por que llegamos aca: KMeans corta arbitrario (comparar_clustering.py), DBSCAN
con un eps global sufre efecto cadena sin importar como se elija ese eps, sea
a ojo (explorar_clustering_v2.py) o con el metodo del codo (afinar_eps.py) -
porque la sismicidad chilena es un gradiente de densidad continuo a lo largo
de la fosa, no un conjunto de blobs separables por un solo umbral de distancia.

HDBSCAN no necesita un eps fijo: construye una jerarquia de densidades y extrae
como clusters los grupos que son "estables" a traves de distintos niveles de
densidad, permitiendo que convivan zonas muy activas y zonas moderadamente
activas como clusters separados. El parametro clave pasa a ser
`min_cluster_size` (tamano minimo para que un grupo cuente como cluster real),
no un radio de distancia.

Resultado con min_cluster_size=20, min_samples=8 (sobre lat/lon estandarizados):
65 clusters geograficamente coherentes (franjas alargadas siguiendo la fosa,
sin conectar zonas realmente separadas como el extremo sur), 33.9% de ruido
(sismos aislados - esperable y aceptable con este metodo). Los dos clusters
mas grandes (lat=-21.16,lon=-68.82 y lat=-24.15,lon=-67.05) coinciden con el
hotspot de mayor densidad que habia encontrado el KDE de forma independiente
en explorar_clustering_v2.py (lat=-24.11, lon=-67.02) - validacion cruzada
entre dos metodos distintos.

Decision final para el pipeline de produccion (scripts/actualizar_historico.py):
HDBSCAN(min_cluster_size=20, min_samples=8) sobre [lat, lon] estandarizados
con StandardScaler. Ver DECISIONES.md para el detalle completo de la decision.
"""

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import HDBSCAN
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
    rows.append({"lat": lat, "lon": lon, "depth": depth, "mag": f["properties"]["mag"]})

df = pd.DataFrame(rows).dropna(subset=["lat", "lon", "mag"])
X = df[["lat", "lon"]].values
scaler = StandardScaler()
Xs = scaler.fit_transform(X)

# --- 1. Barrido de min_cluster_size para ver sensibilidad ---
print("\n=== Barrido de min_cluster_size (HDBSCAN) ===")
print(f"{'min_cluster_size':>17} | {'n_clusters':>10} | {'cluster mas grande':>18} | {'% en ese cluster':>16} | {'% ruido':>8}")
for mcs in [10, 15, 20, 30, 50, 80, 120]:
    hdb = HDBSCAN(min_cluster_size=mcs, min_samples=8)
    labels = hdb.fit_predict(Xs)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    if n_clusters > 0:
        sizes = pd.Series(labels[labels != -1]).value_counts()
        biggest = sizes.max()
    else:
        biggest = 0
    print(f"{mcs:17d} | {n_clusters:10d} | {biggest:18d} | {100*biggest/len(df):15.1f}% | {100*n_noise/len(df):7.1f}%")

# --- 2. Quedarnos con un min_cluster_size razonable y ver el detalle ---
MIN_CLUSTER_SIZE = 20
hdb_final = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, min_samples=8)
df["hdbscan_cluster"] = hdb_final.fit_predict(Xs)

print(f"\n=== Detalle con min_cluster_size={MIN_CLUSTER_SIZE} ===")
resumen = df[df["hdbscan_cluster"] != -1].groupby("hdbscan_cluster").agg(
    n=("mag", "size"), lat_centro=("lat", "mean"), lon_centro=("lon", "mean"), mag_media=("mag", "mean"),
).sort_values("n", ascending=False)
print(resumen)
print(f"Ruido: {(df['hdbscan_cluster'] == -1).sum()} sismos ({100*(df['hdbscan_cluster'] == -1).mean():.1f}%)")

# --- 3. Grafico comparativo: clusters de HDBSCAN sobre el mapa (lon/lat) ---
plt.figure(figsize=(6, 10))
noise = df[df["hdbscan_cluster"] == -1]
plt.scatter(noise["lon"], noise["lat"], s=4, c="lightgray", label="ruido")
clustered = df[df["hdbscan_cluster"] != -1]
scatter = plt.scatter(clustered["lon"], clustered["lat"], s=6, c=clustered["hdbscan_cluster"], cmap="tab20")
plt.title(f"HDBSCAN (min_cluster_size={MIN_CLUSTER_SIZE}) - mag>=4.0, 2015-2026")
plt.xlabel("Longitud")
plt.ylabel("Latitud")
plt.legend()
plt.tight_layout()
plt.savefig("hdbscan_clusters.png", dpi=120)
plt.show()
print("\nGuardado: hdbscan_clusters.png")

df.to_csv("sismos_hdbscan.csv", index=False)
print("Guardado: sismos_hdbscan.csv")
