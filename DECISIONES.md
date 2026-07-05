# Decisiones de diseño

Registro técnico de las decisiones tomadas durante la construcción de este proyecto y por qué se tomaron. Pensado para quien quiera entender el razonamiento completo, no solo el resultado final (ver [`README.md`](README.md) para eso).

## Objetivo del proyecto

Proyecto de portafolio que combina datos geoespaciales, Python/ML y frontend: un mapa interactivo de sismos en Chile, en tiempo real e histórico, con una capa de Machine Learning. Debe quedar 100% funcional en GitHub Pages (sitio estático, sin backend).

## Fuente de datos

API de USGS (Servicio Geológico de EE.UU.), filtrada a territorio chileno. No se usa el CSN de la Universidad de Chile porque no tiene API — solo HTML para raspar y coordenadas en texto libre, lo cual es frágil.

Endpoint base:
```
https://earthquake.usgs.gov/fdsnws/event/1/query
```

Bounding box para Chile continental e insular cercano:
```
minlatitude=-56
maxlatitude=-17
minlongitude=-76
maxlongitude=-66
```

Bounding box adicional para Isla de Pascua (Rapa Nui), fuera del rango anterior:
```
minlatitude=-29
maxlatitude=-25
minlongitude=-111
maxlongitude=-107
```

Nota: se usan dos bounding boxes separados en vez de uno solo ampliado, porque un único rectángulo que cubra ambas zonas incluiría ~45° de longitud de océano Pacífico intermedio, capturando sismicidad de dorsales oceánicas sin relación con Chile.

La Antártica Chilena (territorio reclamado al sur del paralelo -60°) queda fuera de alcance de este proyecto: se solapa con reclamos de otros países y su sismicidad no es representativa de la actividad tectónica chilena continental.

## Arquitectura (híbrida)

1. **Vista "Ahora" (tiempo real):** el frontend (JavaScript vanilla) llama directo a la API de USGS con `fetch()` al cargar la página. Sin backend, sin key. Muestra sismos de las últimas 24-72 horas en un mapa con Leaflet.js, marcadores por magnitud.
2. **Vista "Histórico":** un script Python (pandas + scikit-learn) descarga y procesa años de datos históricos, aplica clustering **HDBSCAN** (no KMeans) para identificar zonas de mayor actividad sísmica, y genera dos JSON estáticos — `data/historico_clusters.json` (liviano, se carga siempre) y `data/historico_eventos.json` (pesado, se carga bajo demanda) — con el resultado ya procesado. El frontend solo lee esos JSON, no llama a la API en vivo para esta vista.
3. **Automatización:** GitHub Actions con `schedule` (cron) corre el script Python periódicamente (ej. 1 vez por semana), regenera ambos JSON, y hace commit automático al repo si hay cambios. Repo debe ser público para que las Actions sean gratis sin límite de minutos.

### Decisión de clustering: HDBSCAN en vez de KMeans/DBSCAN

Se exploraron tres algoritmos con datos reales de USGS (10,673 sismos, mag≥4.0, 2015-2026, `scripts/exploracion/`) antes de decidir:

- **KMeans** fuerza un número fijo de clusters (`k`) sobre datos que forman una franja larga y angosta (la fosa de subducción), generando cortes geográficos arbitrarios sin relación con la actividad real.
- **DBSCAN** con un `eps` global sufre "efecto cadena": como la sismicidad es densa y continua a lo largo de toda la costa, casi cualquier `eps` razonable conecta el 90%+ de los sismos en un solo cluster gigante. Se probó incluso el método estándar del "codo" (k-distance plot) para elegir `eps` automáticamente, pero encuentra el punto donde termina la masa conectada y empiezan los outliers extremos (eps≈0.13, 96% en un cluster) — no el punto que separa la franja en sub-zonas útiles. Un `eps` manual más chico (~0.04-0.06) sí fragmenta en zonas razonables, pero es una elección arbitraria sin justificación rigurosa.
- **HDBSCAN** (jerárquico, sin `eps` fijo) resolvió el problema: construye una jerarquía de densidades y extrae clusters estables de distinto tamaño/densidad sin forzar un umbral global. Con `min_cluster_size=20, min_samples=8` produjo 65 clusters geográficamente coherentes (franjas alargadas siguiendo la fosa, zonas aisladas en el sur sin forzar conexión) y 33.9% de ruido (sismos aislados, esperable con este método). Los dos clusters más grandes coinciden con el hotspot de mayor densidad encontrado independientemente vía KDE (lat≈-24, lon≈-67), validación cruzada entre métodos.

Parámetros finales recomendados: `HDBSCAN(min_cluster_size=20, min_samples=8)` sobre `[lat, lon]` estandarizados con `StandardScaler`.

Ver `scripts/exploracion/` para el proceso completo (4 scripts documentados en orden) que llevó a esta decisión.

### Formato final: dos archivos separados (`historico_clusters.json` + `historico_eventos.json`)

Se probó primero un solo `data/historico.json` con todo junto (metadata + clusters + eventos), pero pesaba ~2.8MB sin comprimir / ~295KB con gzip — y ese peso se pagaba siempre, aunque el usuario nunca hiciera clic en un cluster. Se decidió separar en dos archivos:

- **`data/historico_clusters.json`** (~14KB sin comprimir / ~2KB con gzip): metadata + resumen de clusters (~65 items). El frontend lo carga siempre al entrar a la vista Histórico — es lo que se pinta por defecto.
- **`data/historico_eventos.json`** (~2.8MB sin comprimir / ~280KB con gzip): lista completa de eventos individuales (miles de items). El frontend lo carga bajo demanda, recién cuando el usuario hace clic en un cluster por primera vez (o se puede precargar en segundo plano después del render inicial, sin bloquearlo).

```json
// data/historico_clusters.json
{
  "metadata": {
    "generado": "2026-07-04T00:00:00Z",
    "fuente": "https://earthquake.usgs.gov/fdsnws/event/1/query",
    "rango_fechas": { "desde": "2015-01-01", "hasta": "2026-07-04" },
    "clustering": {
      "algoritmo": "HDBSCAN",
      "min_cluster_size": 20,
      "min_samples": 8
    },
    "criterio_posible_replica": "cluster != -1 y menos de 1 hora desde el evento anterior del mismo cluster",
    "total_eventos": 10673,
    "total_clusters": 65
  },
  "clusters": [
    {
      "id": 55,
      "region": "continental",
      "lat": -21.16,
      "lon": -68.82,
      "n": 1478,
      "mag_media": 4.35,
      "mag_max": 6.1,
      "fecha_ultimo_evento": "2026-05-12T03:22:10Z"
    }
  ]
}
```

```json
// data/historico_eventos.json
{
  "eventos": [
    {
      "id": "us6000t9qu",
      "lat": -20.6993,
      "lon": -67.3066,
      "depth": 221.15,
      "mag": 4.0,
      "magType": "mb",
      "fecha": "2026-06-27T14:11:03Z",
      "place": "56 km WSW of Uyuni, Bolivia",
      "region": "continental",
      "cluster": 1,
      "posible_replica": false
    }
  ]
}
```

Decisiones de diseño del schema:

- **Archivos separados en vez de uno solo**, unidos por el campo `cluster`: prioriza que la carga inicial de la vista Histórico sea liviana (~2KB) sobre tener todo en un único archivo. La reducción de tamaño ataca el problema real (cuánto hay que bajar *antes de que el usuario vea algo*), a diferencia de minificar el JSON (quitar indentado), que con gzip aplicado apenas ahorra un ~6% porque gzip ya comprime muy bien los espacios en blanco.
- **`region: "continental" | "isla_pascua"`** en cada evento y cluster. Isla de Pascua nunca genera un cluster real (~3 sismos en 10 años, muy por debajo de `min_cluster_size=20`): sus eventos siempre quedan con `cluster: -1` y se muestran como puntos individuales sueltos.
- **`cluster: -1`** marca sismos que HDBSCAN clasificó como ruido (~34% del total) — se muestran como puntos individuales, no agrupados.
- **`posible_replica`** (booleano, por evento): `true` si el evento pertenece a un cluster real (`cluster != -1`) y ocurrió a menos de 1 hora del evento anterior de ese mismo cluster. Es un campo **descriptivo, no predictivo** — clasifica algo que ya ocurrió, no anticipa sismos futuros. Los eventos con `cluster: -1` quedan siempre en `false` (no tiene sentido buscar réplicas en sismos aislados). La regla exacta queda documentada en `metadata.criterio_posible_replica`.
- **`fecha` en formato ISO 8601**, no el timestamp en milisegundos que entrega USGS — se parsea directo con `new Date()` en JS.
- **`magType`** incluido por transparencia (distintas escalas de magnitud —mb, ml, mw— no son directamente comparables), aunque no se usa activamente en la versión inicial del frontend.
- Objetos con nombres de campo explícitos (no arrays posicionales) dentro de cada archivo: prioriza legibilidad para portafolio sobre una optimización marginal adicional de tamaño.

### Manejo de fallos al actualizar el histórico

Si la API de USGS falla (timeout, error HTTP, respuesta vacía) durante la corrida semanal del cron:

- El script debe **reintentar** la descarga un par de veces con espera entre intentos antes de rendirse.
- Si sigue fallando, el script **debe abortar sin escribir ningún archivo**, dejando intactos `data/historico_clusters.json` y `data/historico_eventos.json` de la corrida anterior exitosa — nunca commitear un JSON vacío o parcial.
- El script debe salir con código de error distinto de cero, para que el workflow de GitHub Actions quede marcado como fallido (GitHub notifica por email automáticamente al dueño del repo en crons fallidos, sin configuración extra).
- Regla de implementación: escribir ambos archivos debe ser el **último paso** del script, después de descargar, validar y procesar todo — así un fallo en cualquier paso previo deja los archivos buenos anteriores sin tocar, sin necesitar lógica de "restaurar backup".

## Decisiones del frontend

- **Carga perezosa de eventos:** `historico_eventos.json` (~2.8MB) solo se descarga cuando hace falta — al hacer clic en un cluster por primera vez, o al elegir un filtro por año — y queda cacheado en memoria para el resto de la sesión. La vista Histórico por defecto solo carga `historico_clusters.json` (~14KB).
- **Filtro "Este año" / "Año anterior" sin agrupar:** dentro de la vista Histórico, un dropdown permite ver los eventos individuales de una ventana de tiempo acotada (~1000-1700 eventos) sin pasar por el clustering. Es puramente un filtro en el navegador sobre datos ya descargados — **no le agrega carga a GitHub Actions**, el cron semanal de HDBSCAN no cambia. Se limita a 2 años (no a los 10 años completos) precisamente para no reintroducir el problema de performance que el clustering resolvió.
- **Manejo de errores de red:** tanto la vista "Ahora" (fetch en vivo a USGS) como la carga de `historico_eventos.json` muestran un mensaje visible al usuario si el fetch falla, en vez de fallar en silencio.
- **Diseño mobile-first:** `100dvh` para evitar el bug de altura con la barra de direcciones en Safari/Chrome móvil, botones con mínimo 44px de alto (objetivo táctil), `flex-wrap` en la barra superior.
- **Modal informativo:** explica la fuente de datos y la metodología (HDBSCAN, detección de réplicas) y deja explícito que el mapa es **descriptivo, no predictivo** — no predice cuándo, dónde o con qué magnitud ocurrirá un próximo sismo.

## Stack técnico

- Frontend: HTML + CSS + JS vanilla (sin frameworks), diseño simple y minimalista
- Mapa: Leaflet.js
- Procesamiento: Python con `requests`, `pandas`, `scikit-learn`
- Automatización: GitHub Actions (`.github/workflows/actualizar-sismos.yml`)
- Hosting: GitHub Pages

## Estructura de archivos

```
/
├── index.html              # página principal con el mapa
├── css/
│   └── style.css
├── js/
│   └── app.js               # fetch a USGS + lógica del mapa + toggle Ahora/Histórico
├── data/
│   ├── historico_clusters.json   # generado por el script Python (liviano, carga siempre)
│   └── historico_eventos.json    # generado por el script Python (pesado, carga bajo demanda)
├── scripts/
│   ├── actualizar_historico.py   # descarga USGS + limpieza + clustering + exporta ambos JSON
│   └── exploracion/               # proceso de investigacion que llevo a elegir HDBSCAN
├── .github/
│   └── workflows/
│       └── actualizar-sismos.yml
├── README.md                 # overview del proyecto, cómo correrlo y desplegarlo
└── DECISIONES.md              # este archivo
```

## Estado actual

- [x] Exploración de clustering (`scripts/exploracion/`)
- [x] `scripts/actualizar_historico.py`
- [x] `index.html`, `css/style.css`, `js/app.js`
- [x] `.github/workflows/actualizar-sismos.yml` — probado con `workflow_dispatch`, corrió en ~25s y commiteó los datos actualizados automáticamente
- [x] Desplegado en GitHub Pages: https://holapancho.github.io/app-sismos-cl/

Proyecto funcionalmente completo. Próximos pasos serían mejoras incrementales, no piezas faltantes.
