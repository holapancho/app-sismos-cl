"""
Paso 3 de la exploracion de clustering: en vez de elegir eps a ojo (como en
explorar_clustering_v2.py), este script intenta encontrarlo de forma rigurosa
con el metodo estandar del "codo" (k-distance plot): para cada punto se mide
la distancia a su 8vo vecino mas cercano, se ordenan esas distancias, y se
busca el punto de maxima curvatura.

Resultado (documentado aca porque es un hallazgo negativo importante, no un
bug a repetir): el metodo encontro eps=0.1279, que cae justo en el regimen
"cluster gigante" (96.4% de los sismos en un solo grupo). Esto NO es un error
de calculo (una vez corregido el signo del argmin/argmax, ver comentario en el
codigo) - es que el k-distance plot de este dataset tiene un solo quiebre
geometrico nitido, y ese quiebre separa "la masa conectada" de "outliers
extremos", no "zona A" de "zona B" dentro de la masa conectada. La fosa
sismica chilena es un gradiente de densidad continuo, no un conjunto de blobs
discretos, asi que no existe un eps global que la corte en sub-zonas de forma
matematicamente "correcta".

Conclusion: para este dominio, un eps unico (DBSCAN) no es la herramienta
adecuada aunque se elija con un metodo riguroso. La solucion fue cambiar de
algoritmo, no de parametro - ver hdbscan_exploracion.py.
"""

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors

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

MIN_SAMPLES = 8

# --- 1. k-distance plot: distancia al min_samples-esimo vecino mas cercano, ordenada ---
nn = NearestNeighbors(n_neighbors=MIN_SAMPLES)
nn.fit(Xs)
distances, _ = nn.kneighbors(Xs)
k_dist = np.sort(distances[:, -1])

# --- 2. Encontrar el "codo" (metodo de maxima distancia a la recta entre extremos) ---
n = len(k_dist)
x = np.arange(n)
y = k_dist
x_norm = (x - x.min()) / (x.max() - x.min())
y_norm = (y - y.min()) / (y.max() - y.min())
dist_a_recta = y_norm - x_norm
idx_codo = np.argmin(dist_a_recta)  # la curva se mantiene baja y luego sube de golpe: el codo esta en el minimo, no en el maximo
eps_codo = k_dist[idx_codo]

print(f"\nCodo detectado en el punto {idx_codo} de {n}")
print(f"eps sugerido por el metodo del codo: {eps_codo:.4f} (en espacio escalado)")

# --- 3. Barrido fino alrededor del codo sugerido ---
print("\n=== Barrido fino de eps alrededor del codo ===")
print(f"{'eps':>7} | {'n_clusters':>10} | {'cluster mas grande':>18} | {'% en ese cluster':>16} | {'% ruido':>8}")
candidatos = sorted(set([round(eps_codo * f, 4) for f in [0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.5, 2.0]]))
for eps in candidatos:
    db = DBSCAN(eps=eps, min_samples=MIN_SAMPLES).fit(Xs)
    labels = db.labels_
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    sizes = pd.Series(labels[labels != -1]).value_counts() if n_clusters > 0 else pd.Series([0])
    biggest = sizes.max()
    print(f"{eps:7.4f} | {n_clusters:10d} | {biggest:18d} | {100*biggest/len(df):15.1f}% | {100*n_noise/len(df):7.1f}%")

# --- 4. Graficar el k-distance plot con el codo marcado ---
plt.figure(figsize=(8, 5))
plt.plot(k_dist, label="distancia al 8vo vecino (ordenada)")
plt.axhline(eps_codo, color="red", linestyle="--", label=f"eps sugerido = {eps_codo:.4f}")
plt.axvline(idx_codo, color="red", linestyle=":")
plt.xlabel("Puntos ordenados por distancia")
plt.ylabel("Distancia (espacio escalado)")
plt.title("k-distance plot para elegir eps de DBSCAN")
plt.legend()
plt.tight_layout()
plt.savefig("k_distance_plot.png", dpi=120)
plt.show()
print("\nGuardado: k_distance_plot.png")

# --- 5. Detalle final con el eps del codo ---
db_final = DBSCAN(eps=eps_codo, min_samples=MIN_SAMPLES).fit(Xs)
df["dbscan_cluster"] = db_final.labels_
print(f"\n=== Detalle final con eps={eps_codo:.4f} (elegido por metodo del codo) ===")
resumen = df[df["dbscan_cluster"] != -1].groupby("dbscan_cluster").agg(
    n=("mag", "size"), lat_centro=("lat", "mean"), lon_centro=("lon", "mean"), mag_media=("mag", "mean"),
).sort_values("n", ascending=False)
print(resumen.head(15))
print(f"Ruido: {(df['dbscan_cluster'] == -1).sum()} sismos ({100*(df['dbscan_cluster'] == -1).mean():.1f}%)")
