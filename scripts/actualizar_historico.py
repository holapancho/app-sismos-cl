"""
Descarga el historico sismico de Chile desde USGS, aplica clustering HDBSCAN
para detectar zonas de mayor actividad, calcula el flag de posibles replicas,
y genera dos archivos siguiendo el schema documentado en DECISIONES.md:

- data/historico_clusters.json: metadata + resumen de clusters (~65 items,
  liviano). El frontend lo carga siempre al entrar a la vista Historico.
- data/historico_eventos.json: lista completa de eventos individuales
  (~miles de items, mas pesado). El frontend lo carga bajo demanda, recien
  cuando el usuario hace clic en un cluster.

Ver scripts/exploracion/ para el proceso (KMeans -> DBSCAN -> HDBSCAN) que
llevo a elegir estos parametros.

Si la descarga de USGS falla, el script aborta SIN escribir ningun archivo,
para dejar intactos los archivos de la corrida anterior (ver seccion "Manejo
de fallos" en DECISIONES.md).
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from sklearn.cluster import HDBSCAN
from sklearn.preprocessing import StandardScaler

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
MIN_MAGNITUDE = 4.0
ANIOS_HISTORICO = 10
MIN_CLUSTER_SIZE = 20
MIN_SAMPLES = 8
VENTANA_REPLICA_HORAS = 1
MAX_REINTENTOS = 3
ESPERA_BASE_SEGUNDOS = 5

BBOX_CONTINENTAL = {
    "minlatitude": -56,
    "maxlatitude": -17,
    "minlongitude": -76,
    "maxlongitude": -66,
}
BBOX_ISLA_PASCUA = {
    "minlatitude": -29,
    "maxlatitude": -25,
    "minlongitude": -111,
    "maxlongitude": -107,
}

RUTA_CLUSTERS = Path(__file__).resolve().parent.parent / "data" / "historico_clusters.json"
RUTA_EVENTOS = Path(__file__).resolve().parent.parent / "data" / "historico_eventos.json"


def descargar_sismos(bbox, region, desde, hasta):
    params = {
        "format": "geojson",
        "starttime": desde,
        "endtime": hasta,
        "minmagnitude": MIN_MAGNITUDE,
        **bbox,
    }
    ultimo_error = None
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            resp = requests.get(USGS_URL, params=params, timeout=60)
            resp.raise_for_status()
            features = resp.json().get("features", [])
            print(f"[{region}] descargados {len(features)} sismos (intento {intento})")
            return features
        except (requests.RequestException, ValueError) as err:
            ultimo_error = err
            print(f"[{region}] fallo intento {intento}/{MAX_REINTENTOS}: {err}")
            if intento < MAX_REINTENTOS:
                time.sleep(ESPERA_BASE_SEGUNDOS * intento)
    raise RuntimeError(
        f"No se pudo descargar datos de USGS para {region} tras {MAX_REINTENTOS} intentos"
    ) from ultimo_error


def features_a_dataframe(features, region):
    filas = []
    for f in features:
        lon, lat, depth = f["geometry"]["coordinates"]
        props = f["properties"]
        filas.append({
            "id": f["id"],
            "lat": lat,
            "lon": lon,
            "depth": depth,
            "mag": props.get("mag"),
            "magType": props.get("magType"),
            "place": props.get("place"),
            "time_ms": props.get("time"),
            "region": region,
        })
    return pd.DataFrame(filas)


def calcular_clusters_continental(df):
    """HDBSCAN solo sobre la region continental. Isla de Pascua queda
    siempre como ruido (-1): con ~3 sismos en 10 anios no alcanza el
    min_cluster_size=20 para formar un cluster real (ver scripts/exploracion/).
    """
    df["cluster"] = -1
    mask_continental = df["region"] == "continental"
    if mask_continental.sum() >= MIN_SAMPLES:
        X = df.loc[mask_continental, ["lat", "lon"]].values
        Xs = StandardScaler().fit_transform(X)
        modelo = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES)
        df.loc[mask_continental, "cluster"] = modelo.fit_predict(Xs)
    return df


def calcular_posible_replica(df):
    df = df.sort_values("fecha").reset_index(drop=True)
    df["posible_replica"] = False
    for _, sub in df[df["cluster"] != -1].groupby("cluster"):
        horas_desde_anterior = sub["fecha"].diff().dt.total_seconds() / 3600
        idx_replicas = sub.index[horas_desde_anterior < VENTANA_REPLICA_HORAS]
        df.loc[idx_replicas, "posible_replica"] = True
    return df


def construir_clusters_resumen(df):
    clusters = []
    for cluster_id, sub in df[df["cluster"] != -1].groupby("cluster"):
        clusters.append({
            "id": int(cluster_id),
            "region": sub["region"].iloc[0],
            "lat": round(float(sub["lat"].mean()), 4),
            "lon": round(float(sub["lon"].mean()), 4),
            "n": int(len(sub)),
            "mag_media": round(float(sub["mag"].mean()), 2),
            "mag_max": round(float(sub["mag"].max()), 2),
            "fecha_ultimo_evento": sub["fecha"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return sorted(clusters, key=lambda c: c["n"], reverse=True)


def construir_eventos(df):
    eventos = []
    for _, row in df.iterrows():
        eventos.append({
            "id": row["id"],
            "lat": round(float(row["lat"]), 4),
            "lon": round(float(row["lon"]), 4),
            "depth": round(float(row["depth"]), 2) if pd.notna(row["depth"]) else None,
            "mag": round(float(row["mag"]), 2),
            "magType": row["magType"],
            "fecha": row["fecha"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "place": row["place"],
            "region": row["region"],
            "cluster": int(row["cluster"]),
            "posible_replica": bool(row["posible_replica"]),
        })
    return eventos


def main():
    hasta = datetime.now(timezone.utc)
    desde = hasta - timedelta(days=365 * ANIOS_HISTORICO)
    fmt = "%Y-%m-%d"

    try:
        features_continental = descargar_sismos(
            BBOX_CONTINENTAL, "continental", desde.strftime(fmt), hasta.strftime(fmt)
        )
        features_isla_pascua = descargar_sismos(
            BBOX_ISLA_PASCUA, "isla_pascua", desde.strftime(fmt), hasta.strftime(fmt)
        )
    except RuntimeError as err:
        print(f"ERROR: {err}")
        print("Se conserva data/historico.json existente sin cambios.")
        sys.exit(1)

    df = pd.concat([
        features_a_dataframe(features_continental, "continental"),
        features_a_dataframe(features_isla_pascua, "isla_pascua"),
    ], ignore_index=True)

    df = df.dropna(subset=["lat", "lon", "mag"])
    if df.empty:
        print("ERROR: USGS devolvio 0 sismos validos. Se aborta sin escribir el JSON.")
        sys.exit(1)

    df["fecha"] = pd.to_datetime(df["time_ms"], unit="ms", utc=True)
    df = calcular_clusters_continental(df)
    df = calcular_posible_replica(df)

    clusters = construir_clusters_resumen(df)
    eventos = construir_eventos(df)

    metadata = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fuente": USGS_URL,
        "rango_fechas": {"desde": desde.strftime(fmt), "hasta": hasta.strftime(fmt)},
        "clustering": {
            "algoritmo": "HDBSCAN",
            "min_cluster_size": MIN_CLUSTER_SIZE,
            "min_samples": MIN_SAMPLES,
        },
        "criterio_posible_replica": (
            f"cluster != -1 y menos de {VENTANA_REPLICA_HORAS} hora(s) "
            "desde el evento anterior del mismo cluster"
        ),
        "total_eventos": int(len(df)),
        "total_clusters": len(clusters),
    }

    # Dos archivos separados: historico_clusters.json se carga siempre al
    # entrar a la vista Historico (liviano, ~65 items). historico_eventos.json
    # se carga bajo demanda al hacer clic en un cluster (pesa ~2.8MB sin
    # comprimir / ~280KB con gzip, no tiene sentido bajarlo si el usuario
    # nunca hace clic en nada).
    salida_clusters = {"metadata": metadata, "clusters": clusters}
    salida_eventos = {"eventos": eventos}

    RUTA_CLUSTERS.parent.mkdir(parents=True, exist_ok=True)
    RUTA_CLUSTERS.write_text(json.dumps(salida_clusters, ensure_ascii=False, indent=2), encoding="utf-8")
    RUTA_EVENTOS.write_text(json.dumps(salida_eventos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Guardado: {RUTA_CLUSTERS} ({len(clusters)} clusters)")
    print(f"Guardado: {RUTA_EVENTOS} ({len(eventos)} eventos)")


if __name__ == "__main__":
    main()
