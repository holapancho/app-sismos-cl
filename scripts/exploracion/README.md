# Exploración de clustering

Scripts usados para decidir qué algoritmo de clustering usar en el pipeline final (`scripts/actualizar_historico.py`). Cada uno tiene un docstring con el detalle de qué se probó y qué se encontró.

Orden de lectura:

1. `comparar_clustering.py` — KMeans vs DBSCAN con parámetros por defecto.
2. `explorar_clustering_v2.py` — barrido de `eps`, enfoque de densidad (KDE), primer vistazo a temporalidad.
3. `afinar_eps.py` — intento de elegir `eps` con el método del codo (hallazgo negativo: no aplica a este dominio).
4. `hdbscan_exploracion.py` — solución final adoptada.

**Conclusión:** se usa `HDBSCAN(min_cluster_size=20, min_samples=8)` en vez de KMeans/DBSCAN, porque la sismicidad chilena es un gradiente de densidad continuo a lo largo de la fosa, no zonas separables por un radio fijo. Detalle completo de la decisión en [`DECISIONES.md`](../../DECISIONES.md).

## Variables de entrada

Todos los scripts descargan sismos desde la API de USGS (mag ≥ 4.0, 2015-2026) y trabajan con estos campos:

- `lat`, `lon` — coordenadas del sismo (grados). Son las únicas variables usadas para el clustering.
- `depth` — profundidad del hipocentro (km).
- `mag` — magnitud.
- `place` — descripción textual de la ubicación (solo informativo, no se usa en el clustering).
- `time_ms` / `fecha` — timestamp de USGS (ms desde epoch) convertido a datetime; se guarda para análisis temporal futuro (detección de réplicas), no se usa en el clustering espacial.

Antes de clusterizar, `lat`/`lon` se estandarizan con `StandardScaler` (media 0, desvío 1), porque KMeans/DBSCAN/HDBSCAN miden distancias y sin estandarizar el resultado podría distorsionarse por la escala relativa de cada eje.
