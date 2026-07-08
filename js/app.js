const USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query";
const MIN_MAGNITUD_AHORA = 2.5;
const HORAS_VENTANA_AHORA = 72;

const BBOX_CONTINENTAL = {
  minlatitude: -56,
  maxlatitude: -17,
  minlongitude: -76,
  maxlongitude: -66,
};
const BBOX_ISLA_PASCUA = {
  minlatitude: -29,
  maxlatitude: -25,
  minlongitude: -111,
  maxlongitude: -107,
};

const RUTA_CLUSTERS = "data/historico_clusters.json";
const RUTA_EVENTOS = "data/historico_eventos.json";

const mapa = L.map("map", { zoomControl: true }).setView([-33.45, -70.6], 5);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(mapa);

const capaAhora = L.layerGroup();
const capaClusters = L.layerGroup();
const capaEventosCluster = L.layerGroup();
const capaEventosAnio = L.layerGroup();

let datosAhoraCargados = false;
let clustersCargados = false;
let eventosCache = null;
let eventosCargandoPromesa = null;
let filtroHistoricoActual = "agrupado";

function mostrarMensaje(texto) {
  const el = document.getElementById("mensaje");
  el.textContent = texto;
  el.classList.remove("oculto");
}

function ocultarMensaje() {
  document.getElementById("mensaje").classList.add("oculto");
}

function colorPorMagnitud(mag) {
  if (mag >= 6.5) return "#e74c3c";
  if (mag >= 5.5) return "#e67e22";
  if (mag >= 4.5) return "#f1c40f";
  return "#2ecc71";
}

function radioPorMagnitud(mag) {
  return Math.max(4, mag * 2.2);
}

function formatearFecha(fechaISO) {
  const fecha = new Date(fechaISO);
  return fecha.toLocaleString("es-CL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function popupEvento(props) {
  const replica = props.posible_replica ? "<br>Posible réplica" : "";
  return `
    <div class="popup-sismo">
      <strong>M ${props.mag.toFixed(1)} — ${props.place}</strong>
      Profundidad: ${props.depth != null ? props.depth.toFixed(1) + " km" : "N/D"}<br>
      Fecha: ${formatearFecha(props.fecha)}${replica}
    </div>
  `;
}

async function cargarAhora() {
  if (datosAhoraCargados) return;
  try {
    const hasta = new Date();
    const desde = new Date(hasta.getTime() - HORAS_VENTANA_AHORA * 3600 * 1000);
    const paramsBase = {
      format: "geojson",
      starttime: desde.toISOString(),
      endtime: hasta.toISOString(),
      minmagnitude: MIN_MAGNITUD_AHORA,
    };

    const [respContinental, respIslaPascua] = await Promise.all([
      fetch(`${USGS_URL}?${new URLSearchParams({ ...paramsBase, ...BBOX_CONTINENTAL })}`),
      fetch(`${USGS_URL}?${new URLSearchParams({ ...paramsBase, ...BBOX_ISLA_PASCUA })}`),
    ]);

    if (!respContinental.ok || !respIslaPascua.ok) {
      throw new Error("USGS respondió con error");
    }

    const [dataContinental, dataIslaPascua] = await Promise.all([
      respContinental.json(),
      respIslaPascua.json(),
    ]);

    const features = [...dataContinental.features, ...dataIslaPascua.features];
    features.forEach((f) => {
      const [lon, lat, depth] = f.geometry.coordinates;
      const mag = f.properties.mag;
      L.circleMarker([lat, lon], {
        radius: radioPorMagnitud(mag),
        fillColor: colorPorMagnitud(mag),
        color: "#222",
        weight: 1,
        fillOpacity: 0.8,
      })
        .bindPopup(
          popupEvento({
            ...f.properties,
            depth,
            fecha: new Date(f.properties.time).toISOString(),
          })
        )
        .addTo(capaAhora);
    });

    datosAhoraCargados = true;
    ocultarMensaje();
  } catch (err) {
    console.error("Error cargando vista Ahora:", err);
    mostrarMensaje("No se pudo cargar sismos en tiempo real. Intenta más tarde.");
  }
}

async function cargarClusters() {
  if (clustersCargados) return;
  try {
    const resp = await fetch(RUTA_CLUSTERS);
    if (!resp.ok) throw new Error("No se pudo leer historico_clusters.json");
    const data = await resp.json();

    data.clusters.forEach((cluster) => {
      L.circleMarker([cluster.lat, cluster.lon], {
        radius: Math.max(6, Math.sqrt(cluster.n) * 1.5),
        fillColor: colorPorMagnitud(cluster.mag_media),
        color: "#222",
        weight: 1,
        fillOpacity: 0.6,
      })
        .bindPopup(
          `<div class="popup-sismo">
            <strong>Zona con ${cluster.n} sismos</strong>
            Magnitud media: ${cluster.mag_media.toFixed(1)} (máx ${cluster.mag_max.toFixed(1)})<br>
            Última actividad: ${formatearFecha(cluster.fecha_ultimo_evento)}<br>
            <em>Clic para ver sismos individuales de esta zona</em>
          </div>`
        )
        .on("click", () => mostrarEventosDeCluster(cluster.id))
        .addTo(capaClusters);
    });

    clustersCargados = true;
    ocultarMensaje();
  } catch (err) {
    console.error("Error cargando clusters:", err);
    mostrarMensaje("No se pudo cargar el histórico. Intenta más tarde.");
  }
}

function cargarEventosHistoricos() {
  if (eventosCache) return Promise.resolve(eventosCache);
  if (eventosCargandoPromesa) return eventosCargandoPromesa;

  eventosCargandoPromesa = fetch(RUTA_EVENTOS)
    .then((resp) => {
      if (!resp.ok) throw new Error("No se pudo leer historico_eventos.json");
      return resp.json();
    })
    .then((data) => {
      eventosCache = data.eventos;
      return eventosCache;
    })
    .catch((err) => {
      console.error("Error cargando eventos historicos:", err);
      mostrarMensaje("No se pudieron cargar los sismos de esta zona. Intenta más tarde.");
      eventosCargandoPromesa = null;
      throw err;
    });

  return eventosCargandoPromesa;
}

async function mostrarEventosDeCluster(clusterId) {
  try {
    const eventos = await cargarEventosHistoricos();
    capaEventosCluster.clearLayers();
    eventos
      .filter((e) => e.cluster === clusterId)
      .forEach((evento) => marcarEvento(evento, capaEventosCluster));
    if (!mapa.hasLayer(capaEventosCluster)) capaEventosCluster.addTo(mapa);
    ocultarMensaje();
  } catch (err) {
    // El mensaje de error ya se muestra dentro de cargarEventosHistoricos
  }
}

function marcarEvento(evento, capaDestino) {
  L.circleMarker([evento.lat, evento.lon], {
    radius: radioPorMagnitud(evento.mag),
    fillColor: colorPorMagnitud(evento.mag),
    color: "#222",
    weight: 1,
    fillOpacity: 0.8,
  })
    .bindPopup(popupEvento(evento))
    .addTo(capaDestino);
}

async function mostrarEventosPorAnio(anio) {
  try {
    mostrarMensaje(`Cargando sismos de ${anio}...`);
    const eventos = await cargarEventosHistoricos();
    capaEventosAnio.clearLayers();
    eventos
      .filter((e) => new Date(e.fecha).getFullYear() === anio)
      .forEach((evento) => marcarEvento(evento, capaEventosAnio));
    if (!mapa.hasLayer(capaEventosAnio)) capaEventosAnio.addTo(mapa);
    ocultarMensaje();
  } catch (err) {
    // El mensaje de error ya se muestra dentro de cargarEventosHistoricos
  }
}

function actualizarVistaHistorico() {
  mapa.removeLayer(capaClusters);
  mapa.removeLayer(capaEventosCluster);
  mapa.removeLayer(capaEventosAnio);

  if (filtroHistoricoActual === "agrupado") {
    capaClusters.addTo(mapa);
    if (!clustersCargados) {
      mostrarMensaje("Cargando histórico...");
      cargarClusters();
    }
  } else {
    const anioActual = new Date().getFullYear();
    const anioObjetivo = filtroHistoricoActual === "este_anio" ? anioActual : anioActual - 1;
    mostrarEventosPorAnio(anioObjetivo);
  }
}

function activarVista(vista) {
  document.getElementById("btn-ahora").classList.toggle("activo", vista === "ahora");
  document.getElementById("btn-historico").classList.toggle("activo", vista === "historico");
  
  // Actualizar aria-selected para lectores de pantalla
  const btnAhora = document.getElementById("btn-ahora");
  const btnHistorico = document.getElementById("btn-historico");
  if (vista === "ahora") {
    btnAhora.setAttribute('aria-selected', 'true');
    btnHistorico.setAttribute('aria-selected', 'false');
  } else {
    btnAhora.setAttribute('aria-selected', 'false');
    btnHistorico.setAttribute('aria-selected', 'true');
  }
  
  document.getElementById("controles-historico").classList.toggle("oculto", vista !== "historico");
  ocultarMensaje();

  if (vista === "ahora") {
    mapa.removeLayer(capaClusters);
    mapa.removeLayer(capaEventosCluster);
    mapa.removeLayer(capaEventosAnio);
    capaAhora.addTo(mapa);
    if (!datosAhoraCargados) {
      mostrarMensaje("Cargando sismos en tiempo real...");
      cargarAhora();
    }
  } else {
    mapa.removeLayer(capaAhora);
    actualizarVistaHistorico();
  }
}

document.getElementById("btn-ahora").addEventListener("click", () => activarVista("ahora"));
document.getElementById("btn-historico").addEventListener("click", () => activarVista("historico"));
document.getElementById("filtro-historico").addEventListener("change", (evento) => {
  filtroHistoricoActual = evento.target.value;
  actualizarVistaHistorico();
});

const modalInfo = document.getElementById("modal-info");
const modalOverlay = modalInfo.parentElement;
const btnCerrar = document.getElementById("btn-cerrar-info");
const btnInfo = document.getElementById("btn-info");

function trampaFoco(modal) {
  const focusableSelectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const elementosEnfocables = modal.querySelectorAll(focusableSelectors);
  
  if (elementosEnfocables.length === 0) return;

  const primerElemento = elementosEnfocables[0];
  const ultimoElemento = elementosEnfocables[elementosEnfocables.length - 1];

  function manejarTab(evento) {
    if (evento.key !== 'Tab') return;

    if (evento.shiftKey && evento.target === primerElemento) {
      evento.preventDefault();
      ultimoElemento.focus();
    } else if (!evento.shiftKey && evento.target === ultimoElemento) {
      evento.preventDefault();
      primerElemento.focus();
    }
  }

  modal.addEventListener('keydown', manejarTab);

  return () => modal.removeEventListener('keydown', manejarTab);
}

function abrirModalInfo() {
  modalInfo.classList.remove("oculto");
  modalOverlay.removeAttribute('aria-hidden');
  
  // Trampa de foco: cuando se abre, enfocar el botón cerrar y capturar Tab
  const removerListener = trampaFoco(modalOverlay);
  
  btnCerrar.focus();
}

function cerrarModalInfo() {
  modalInfo.classList.add("oculto");
  modalOverlay.setAttribute('aria-hidden', 'true');
  
  // Restaurar foco al contenedor del mapa después de un breve delay para que sea visible
  setTimeout(() => document.getElementById("map").focus(), 10);
}

document.getElementById("btn-info").addEventListener("click", abrirModalInfo);
document.getElementById("btn-cerrar-info").addEventListener("click", cerrarModalInfo);
modalOverlay.addEventListener("click", (evento) => {
  if (evento.target === modalOverlay && evento.target !== modalInfo) cerrarModalInfo();
});

// Escuchar Escape para cerrar el modal
document.addEventListener("keydown", (evento) => {
  const modalActivo = !modalInfo.classList.contains("oculto");
  if (evento.key === "Escape" && modalActivo) {
    btnCerrar.focus(); // Mantener foco dentro del modal antes de cerrarlo
    cerrarModalInfo();
  }
});

activarVista("ahora");
