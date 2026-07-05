# Sismos Chile

Mapa interactivo de sismos en Chile, en tiempo real e histórico, con una capa de Machine Learning para detectar zonas de mayor actividad sísmica. Proyecto de portafolio 100% estático (sin backend).

🔗 **Sitio en vivo:** https://holapancho.github.io/app-sismos-cl/

**Estado actual:** desplegado y funcionando. Pipeline de datos históricos, frontend y automatización semanal (GitHub Actions) están completos y probados en producción. Ver [`DECISIONES.md`](DECISIONES.md) para el detalle técnico completo y el registro de qué se decidió y por qué.

## Qué hace

- **Vista "Ahora":** sismos de las últimas 24-72 horas, consultados en vivo directo desde el navegador a la API de USGS.
- **Vista "Histórico":** ~10 años de sismos (magnitud ≥ 4.0), agrupados por zona de actividad usando clustering **HDBSCAN**. Se recalcula semanalmente vía GitHub Actions y se sirve como JSON estático — el sitio nunca llama a USGS para esta vista. Dentro de esta vista también se puede filtrar por "este año" o "año anterior" para ver los sismos individuales sin agrupar.
- **Modal "Acerca de este proyecto"** con la fuente de datos y la metodología, accesible desde el botón ⓘ.

## Fuente de datos

Todos los datos vienen de la API pública de [USGS (United States Geological Survey)](https://earthquake.usgs.gov/fdsnws/event/1/), filtrada a territorio chileno (continental, insular cercano e Isla de Pascua). No se usa el CSN de la Universidad de Chile porque no expone una API — ver [`DECISIONES.md`](DECISIONES.md) para el detalle de los bounding boxes usados y por qué.

## Cómo correr el script de histórico localmente

Requiere Python 3.11+ con `requests`, `pandas` y `scikit-learn`:

```bash
pip install requests pandas scikit-learn
python scripts/actualizar_historico.py
```

Esto descarga el histórico de USGS, aplica el clustering, y genera `data/historico_clusters.json` y `data/historico_eventos.json`. Si la descarga a USGS falla, el script no toca los archivos existentes (ver "Manejo de fallos" en `DECISIONES.md`).

## Cómo desplegar en GitHub Pages

1. Repo público en GitHub (necesario para que GitHub Actions sea gratis sin límite de minutos).
2. Settings → Pages → Source: "Deploy from a branch" (rama `main`, carpeta `/root`).
3. El workflow (`.github/workflows/actualizar-sismos.yml`) ya declara `permissions: contents: write`, así que no hace falta tocar manualmente "Workflow permissions" en Settings → Actions — confirmado corriendo el workflow con `workflow_dispatch`.

## Autor

Francisco Rojas — [LinkedIn](https://www.linkedin.com/in/francisco-rojas-morales-26388a24)

## Licencia

Ver [`LICENSE`](LICENSE).
