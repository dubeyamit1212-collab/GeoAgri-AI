/* ==========================================================
   GeoAgri AI — Dashboard logic
   ========================================================== */

const statusEl = document.getElementById("status-text");

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = kind || "";
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

/* ---------- Map setup ---------- */

const map = L.map("map", { zoomControl: true }).setView([29.3, 75.3], 9);

const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 19,
});

const satelliteLayer = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Tiles &copy; Esri", maxZoom: 19 }
);

osmLayer.addTo(map);

let cropLayer = null;
let boundaryLayer = null;
const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

/* Basemap switcher */
document.querySelectorAll('input[name="basemap"]').forEach((el) => {
  el.addEventListener("change", (e) => {
    if (e.target.value === "osm") {
      map.removeLayer(satelliteLayer);
      osmLayer.addTo(map);
    } else {
      map.removeLayer(osmLayer);
      satelliteLayer.addTo(map);
    }
    if (cropLayer) cropLayer.bringToFront();
  });
});

/* Draw tools (measure / annotate) */
const drawControl = new L.Control.Draw({
  edit: { featureGroup: drawnItems },
  draw: {
    polygon: { showArea: true },
    marker: true,
    rectangle: true,
    polyline: true,
    circle: false,
    circlemarker: false,
  },
});
map.addControl(drawControl);

map.on(L.Draw.Event.CREATED, (e) => {
  drawnItems.addLayer(e.layer);
  if (e.layerType === "polygon" || e.layerType === "rectangle") {
    const areaM2 = L.GeometryUtil ? L.GeometryUtil.geodesicArea(e.layer.getLatLngs()[0]) : null;
    if (areaM2) {
      const ha = (areaM2 / 10000).toFixed(2);
      e.layer.bindPopup(`Area: ${ha} ha`).openPopup();
    }
  }
});

/* Home button: reset view */
const HomeControl = L.Control.extend({
  options: { position: "topleft" },
  onAdd: function () {
    const btn = L.DomUtil.create("button", "leaflet-bar home-btn");
    btn.innerHTML = "🏠";
    btn.title = "Reset view";
    btn.onclick = () => {
      if (window.__rasterBounds) {
        map.fitBounds(window.__rasterBounds);
      } else {
        map.setView([29.3, 75.3], 9);
      }
    };
    return btn;
  },
});
map.addControl(new HomeControl());

/* ---------- Raster info + crop tile layer ---------- */

async function loadRasterInfo() {
  try {
    const info = await fetchJSON("/info");
    document.getElementById("info-width").textContent = info.width;
    document.getElementById("info-height").textContent = info.height;
    document.getElementById("info-bands").textContent = info.bands;
    document.getElementById("info-minzoom").textContent = info.min_zoom;
    document.getElementById("info-maxzoom").textContent = info.max_zoom;

    const b = info.bounds_wgs84; // [left, bottom, right, top]
    const bounds = L.latLngBounds([b[1], b[0]], [b[3], b[2]]);
    window.__rasterBounds = bounds;

    cropLayer = L.tileLayer("/tiles/{z}/{x}/{y}.png", {
      minZoom: info.min_zoom,
      maxZoom: info.max_zoom,
      maxNativeZoom: info.max_zoom,
      bounds: bounds,
      tileSize: info.tile_size,
      opacity: 0.85,
    }).addTo(map);

    map.fitBounds(bounds);
    setStatus("✓ Ready", "ok");
  } catch (err) {
    console.error(err);
    setStatus("⚠ Raster unavailable — " + err.message, "error");
  }
}

/* ---------- District / Village dropdowns ---------- */

const districtSelect = document.getElementById("district-select");
const villageSelect = document.getElementById("village-select");
const showAnalyticsBtn = document.getElementById("show-analytics-btn");

async function loadDistricts() {
  try {
    const data = await fetchJSON("/districts");
    districtSelect.innerHTML = '<option value="">Select District</option>';
    data.districts.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      districtSelect.appendChild(opt);
    });
  } catch (err) {
    console.error(err);
    setStatus("⚠ Could not load districts — " + err.message, "error");
  }
}

districtSelect.addEventListener("change", async () => {
  const district = districtSelect.value;
  villageSelect.innerHTML = '<option value="">Select Village</option>';
  villageSelect.disabled = true;
  showAnalyticsBtn.disabled = true;

  if (!district) return;

  try {
    const data = await fetchJSON(`/villages?district=${encodeURIComponent(district)}`);
    data.villages.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      villageSelect.appendChild(opt);
    });
    villageSelect.disabled = false;

    const boundary = await fetchJSON(`/district_boundary?district=${encodeURIComponent(district)}`);
    drawBoundary(boundary, "#1a4d8f", false);
  } catch (err) {
    console.error(err);
    setStatus("⚠ " + err.message, "error");
  }
});

villageSelect.addEventListener("change", async () => {
  const village = villageSelect.value;
  showAnalyticsBtn.disabled = !village;
  if (!village) return;

  try {
    const boundary = await fetchJSON(`/village_boundary?village=${encodeURIComponent(village)}`);
    drawBoundary(boundary, "#e53935", true);
  } catch (err) {
    console.error(err);
    setStatus("⚠ " + err.message, "error");
  }
});

function drawBoundary(geojson, color, zoomTo) {
  if (boundaryLayer) {
    map.removeLayer(boundaryLayer);
  }
  boundaryLayer = L.geoJSON(geojson, {
    style: { color, weight: 2, fillOpacity: 0.05 },
  }).addTo(map);

  if (zoomTo) {
    map.fitBounds(boundaryLayer.getBounds(), { maxZoom: 14 });
  }
}

/* ---------- Analytics panel ---------- */

const analyticsPanel = document.getElementById("analytics-panel");
const analyticsEmpty = document.getElementById("analytics-empty");
const analyticsContent = document.getElementById("analytics-content");
let lastStats = null;

showAnalyticsBtn.addEventListener("click", async () => {
  const village = villageSelect.value;
  if (!village) return;

  analyticsPanel.hidden = false;
  showAnalyticsBtn.disabled = true;
  showAnalyticsBtn.textContent = "Loading...";

  try {
    const stats = await fetchJSON(`/village_stats?village=${encodeURIComponent(village)}`);
    lastStats = stats;
    renderStats(stats);
  } catch (err) {
    console.error(err);
    setStatus("⚠ " + err.message, "error");
  } finally {
    showAnalyticsBtn.disabled = false;
    showAnalyticsBtn.textContent = "Show Analytics";
  }
});

function renderStats(stats) {
  analyticsEmpty.hidden = true;
  analyticsContent.hidden = false;

  document.getElementById("stat-village-name").textContent = stats.village;
  document.getElementById("stat-district-name").textContent = stats.district;
  document.getElementById("stat-cotton").textContent =
    `${stats.cotton_area_ha} ha (${stats.cotton_percent}%)`;
  document.getElementById("stat-paddy").textContent =
    `${stats.paddy_area_ha} ha (${stats.paddy_percent}%)`;
  document.getElementById("stat-other").textContent =
    `${stats.other_area_ha} ha (${stats.other_percent}%)`;
  document.getElementById("stat-total").textContent = `${stats.village_area_ha} ha`;

  drawPieChart("stat-chart", [
    { label: "Cotton", value: stats.cotton_percent, color: "#ffc107" },
    { label: "Paddy", value: stats.paddy_percent, color: "#2e8b57" },
    { label: "Other", value: stats.other_percent, color: "#9aa5b1" },
  ]);
}

function drawPieChart(canvasId, slices) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const r = Math.min(cx, cy) - 8;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const total = slices.reduce((s, sl) => s + sl.value, 0) || 1;
  let start = -Math.PI / 2;

  slices.forEach((sl) => {
    const angle = (sl.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, start, start + angle);
    ctx.closePath();
    ctx.fillStyle = sl.color;
    ctx.fill();
    start += angle;
  });
}

document.getElementById("export-stats-btn").addEventListener("click", async () => {
  const village = villageSelect.value;
  if (!village) return;
  try {
    const boundary = await fetchJSON(`/village_boundary?village=${encodeURIComponent(village)}`);
    const enriched = { ...boundary, properties_stats: lastStats };
    const blob = new Blob([JSON.stringify(enriched, null, 2)], { type: "application/geo+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${village.replace(/\s+/g, "_")}.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error(err);
    setStatus("⚠ Export failed — " + err.message, "error");
  }
});

/* ---------- Pixel Inspector + mouse coordinates ---------- */

let pixelFetchTimer = null;

map.on("mousemove", (e) => {
  const { lat, lng } = e.latlng;
  document.getElementById("px-lat").textContent = lat.toFixed(6);
  document.getElementById("px-lon").textContent = lng.toFixed(6);

  clearTimeout(pixelFetchTimer);
  pixelFetchTimer = setTimeout(async () => {
    try {
      const data = await fetchJSON(`/pixel?lon=${lng}&lat=${lat}`);
      document.getElementById("px-val").textContent = data.pixel_value;
      document.getElementById("px-crop").textContent = data.crop;
    } catch {
      document.getElementById("px-val").textContent = "—";
      document.getElementById("px-crop").textContent = "Outside raster";
    }
  }, 120);
});

/* ---------- Init ---------- */

(async function init() {
  setStatus("Loading...", "");
  await Promise.all([loadRasterInfo(), loadDistricts()]);
})();
