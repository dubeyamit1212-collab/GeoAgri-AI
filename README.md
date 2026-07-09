# 🌾 GeoAgri AI

**Crop Classification GIS Dashboard** — FastAPI + Rasterio + GeoPandas + Leaflet

GeoAgri AI serves a district/village-level crop classification raster (Cotton, Paddy, Unclassified) as
interactive map tiles, with village-level area statistics, boundary lookups, and a pixel inspector — all
through a lightweight FastAPI backend and a single-page Leaflet dashboard.

---

## ✨ Features

- **Interactive map viewer** — Leaflet-based dashboard with OSM/Satellite basemaps, layer toggles, and
  adjustable raster opacity
- **XYZ tile server** — serves the classified crop raster as PNG tiles, rendered on-the-fly from a
  Cloud-Optimized GeoTIFF (COG) using `rio-tiler`
- **Village & district lookups** — searchable district → village drill-down backed by a village
  boundary shapefile
- **Village-level analytics** — per-village breakdown of Cotton / Paddy / Unclassified / NoData area
  (hectares + %), visualized as a pie chart
- **Pixel inspector** — hover the map to see the classified value at any coordinate
- **GeoJSON export** — download a village's boundary enriched with its computed statistics
- **Draw & measure tools** — polygon/rectangle/marker annotations with live area calculation
- **Health check endpoint** — reports data-loading status for monitoring/ops

---

## 🗂️ Crop Classes

| Pixel Value | Label | Tile Color |
|---|---|---|
| `0` | NoData | transparent |
| `1` | Cotton | gold/yellow |
| `2` | Paddy | green |
| `3` | Unclassified | grey |

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Backend API | [FastAPI](https://fastapi.tiangolo.com/) |
| Raster I/O & tiling | [Rasterio](https://rasterio.readthedocs.io/), [rio-tiler](https://cogeotiff.github.io/rio-tiler/) |
| Vector data | [GeoPandas](https://geopandas.org/), [Shapely](https://shapely.readthedocs.io/) |
| Frontend map | [Leaflet](https://leafletjs.com/), [Leaflet.draw](https://github.com/Leaflet/Leaflet.draw) |
| Templating | Jinja2 |

---

## 📁 Project Structure

```
geoagri-ai/
├── main.py              # FastAPI app: routes, raster/vector logic, tile server
├── templates/
│   └── viewer.html       # Leaflet dashboard (map, sidebar, analytics panel)
├── static/
│   └── style.css          # Dashboard styling
├── data/                  # (optional) local data folder
├── uploads/                # created automatically at startup
└── README.md
```

---

## ⚙️ Requirements

- Python 3.9+
- A classified crop raster as a **Cloud-Optimized GeoTIFF (COG)**, single band, integer-coded
  (0 = NoData, 1 = Cotton, 2 = Paddy, 3 = Unclassified)
- A village boundary **shapefile** with at minimum these attribute columns:
  `District`, `Vill_name`, `STATE_UT`, `Sub_dist`, `Vill_LGD`, `Dist_LGD`

### Install dependencies

```bash
pip install fastapi uvicorn[standard] rasterio geopandas rio-tiler shapely jinja2 numpy
```

---

## 🔧 Configuration

The app reads its data paths from environment variables (falling back to local defaults if unset), so
it can run on any machine without code changes:

| Variable | Purpose | Default |
|---|---|---|
| `GEOAGRI_COG_PATH` | Path to the classified crop raster (COG) | `D:\Raster_Web\data\district_crop_map_COG.tif` |
| `GEOAGRI_VILLAGE_SHP` | Path to the village boundary shapefile (`.shp`) | `C:\Users\amitd\Downloads\HARYANA\...\HARYANA.shp` |
| `GEOAGRI_ALLOWED_ORIGINS` | Comma-separated CORS allowed origins | `*` |

Example:

```bash
export GEOAGRI_COG_PATH="/data/district_crop_map_COG.tif"
export GEOAGRI_VILLAGE_SHP="/data/HARYANA/HARYANA.shp"
export GEOAGRI_ALLOWED_ORIGINS="https://yourdomain.com"
```

---

## 🚀 Running Locally

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

- **Dashboard:** [http://localhost:8000/viewer](http://localhost:8000/viewer)
- **API root:** [http://localhost:8000/](http://localhost:8000/)
- **Health check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Basic service status |
| `GET` | `/viewer` | Serves the Leaflet dashboard |
| `GET` | `/info` | Raster metadata (size, bounds, zoom range) |
| `GET` | `/tiles/{z}/{x}/{y}.png` | XYZ tile server for the classified raster |
| `GET` | `/pixel?lon=&lat=` | Classified value at a coordinate |
| `GET` | `/districts` | List of all districts |
| `GET` | `/villages?district=` | List of villages in a district |
| `GET` | `/village_boundary?village=` | Village polygon (GeoJSON) |
| `GET` | `/district_boundary?district=` | Dissolved district polygon (GeoJSON) |
| `GET` | `/village_stats?village=` | Cotton/Paddy/Unclassified/NoData area breakdown for a village |
| `GET` | `/village_info?village=` | Administrative metadata for a village |
| `GET` | `/district_summary?district=` | Village/subdistrict counts for a district |
| `GET` | `/search_village?query=` | Search villages by name |
| `GET` | `/layers` | Available map layers |
| `GET` | `/viewer_config` | Default viewer settings |
| `GET` | `/health` | Service health / data-loading status |

---

## 🖥️ Dashboard Overview

- **Legend** — Cotton / Paddy / Unclassified color key
- **Location panel** — District → Village cascading dropdowns
- **Village Analytics** — pie chart + area/percentage breakdown, with GeoJSON export
- **Layer switcher** — basemap toggle (OSM / Satellite), crop & boundary layer visibility, raster opacity
  slider
- **Pixel inspector** — live classified value under the cursor
- **Draw tools** — polygon, rectangle, marker, polyline with area measurement

---

## 🗺️ Adjusting Raster Zoom Levels

Tile zoom range is controlled server-side in `main.py`, in the `/info` endpoint:

```python
"min_zoom": 9,
"max_zoom": 20,
```

The dashboard reads these values from `/info` at load time and configures the Leaflet tile layer
accordingly — no frontend changes needed when adjusting.

---

## 📝 License

Add your license of choice here (e.g. MIT).

---

## 👤 Author

**Amit Dubey**
