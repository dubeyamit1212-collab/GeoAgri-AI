"""
==========================================================
GeoAgri AI v2
FastAPI + Rasterio + GeoPandas + Leaflet

Author  : Amit Dubey
Version : 2.0
==========================================================
"""

# ==========================================================
# Imports
# ==========================================================

import logging
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rasterio.mask import mask
from rasterio.warp import transform_bounds
from rio_tiler.io import COGReader
from rio_tiler.utils import render
from shapely.geometry import mapping

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("geoagri")

# ==========================================================
# Project Paths
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ==========================================================
# Configuration (env vars override defaults -> works on any machine)
# ==========================================================

COG_PATH = Path(os.environ.get("GEOAGRI_COG_PATH", DATA_DIR / "district_crop_map_COG.tif"))
VILLAGE_DB = Path(os.environ.get("GEOAGRI_VILLAGE_SHP", DATA_DIR / "HARYANA" / "HARYANA.shp"))

ALLOWED_ORIGINS = os.environ.get("GEOAGRI_ALLOWED_ORIGINS", "*").split(",")

# Pixel value -> crop label. Keep this in one place so /pixel, /village_stats
# and the tile colormap can never drift out of sync with each other.
CROP_LABELS = {0: "NoData", 1: "Cotton", 2: "Paddy"}

# Pixel value -> RGBA. This is what actually paints the tiles; without it
# rio-tiler renders raw 0/1/2 values as near-black grayscale.
TILE_COLORMAP = {
    0: (0, 0, 0, 0),        # NoData -> fully transparent, basemap shows through
    1: (255, 193, 7, 255),  # Cotton -> gold/yellow (matches legend)
    2: (46, 139, 87, 255),  # Paddy  -> green (matches legend)
}

# ==========================================================
# App State (populated at startup, not at import time)
# ==========================================================

class AppState:
    village_gdf = None
    village_db_error = None
    cog_error = None


state = AppState()


def load_village_db():
    if not VILLAGE_DB.exists():
        state.village_db_error = (
            f"Village shapefile not found at '{VILLAGE_DB}'. "
            f"Set GEOAGRI_VILLAGE_SHP env var to the correct .shp path."
        )
        logger.error(state.village_db_error)
        return
    try:
        logger.info("Loading village database from %s ...", VILLAGE_DB)
        state.village_gdf = gpd.read_file(VILLAGE_DB)
        logger.info("Loaded %s villages.", f"{len(state.village_gdf):,}")
    except Exception as exc:  # noqa: BLE001
        state.village_db_error = f"Failed to load village shapefile: {exc}"
        logger.exception(state.village_db_error)


def check_cog():
    if not COG_PATH.exists():
        state.cog_error = (
            f"Raster COG not found at '{COG_PATH}'. "
            f"Set GEOAGRI_COG_PATH env var to the correct .tif path."
        )
        logger.error(state.cog_error)


def require_village_gdf():
    if state.village_gdf is None:
        raise HTTPException(
            status_code=503,
            detail=state.village_db_error or "Village database not loaded.",
        )
    return state.village_gdf


def require_cog():
    if state.cog_error:
        raise HTTPException(status_code=503, detail=state.cog_error)
    return COG_PATH


# ==========================================================
# FastAPI App
# ==========================================================

app = FastAPI(
    title="GeoAgri AI",
    version="2.0",
    description="Crop Classification GIS Dashboard",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    load_village_db()
    check_cog()


# ==========================================================
# Templates / Static
# ==========================================================

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==========================================================
# Home
# ==========================================================

@app.get("/")
def home():
    return {"project": "GeoAgri AI", "version": "2.0", "status": "Running"}


# ==========================================================
# Viewer
# ==========================================================

@app.get("/viewer")
def viewer(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="viewer.html",
        context={}
    )

# ==========================================================
# District List
# ==========================================================

@app.get("/districts")
def get_districts():
    gdf = require_village_gdf()
    districts = sorted(gdf["District"].dropna().unique().tolist())
    return {"status": "success", "count": len(districts), "districts": districts}


# ==========================================================
# Village List
# ==========================================================

@app.get("/villages")
def get_villages(district: str):
    gdf = require_village_gdf()
    subset = gdf[gdf["District"].str.upper() == district.upper()]

    if len(subset) == 0:
        raise HTTPException(status_code=404, detail="District not found.")

    villages = sorted(subset["Vill_name"].dropna().unique().tolist())
    return {
        "status": "success",
        "district": district,
        "count": len(villages),
        "villages": villages,
    }


# ==========================================================
# Village Boundary
# ==========================================================

@app.get("/village_boundary")
def village_boundary(village: str):
    gdf = require_village_gdf()
    subset = gdf[gdf["Vill_name"].str.upper() == village.upper()]

    if len(subset) == 0:
        raise HTTPException(status_code=404, detail="Village not found.")

    if subset.crs is not None:
        subset = subset.to_crs(epsg=4326)

    return JSONResponse(content=subset.__geo_interface__)


# ==========================================================
# District Boundary (Optional)
# ==========================================================

@app.get("/district_boundary")
def district_boundary(district: str):
    gdf = require_village_gdf()
    subset = gdf[gdf["District"].str.upper() == district.upper()]

    if len(subset) == 0:
        raise HTTPException(status_code=404, detail="District not found.")

    district_polygon = subset.dissolve(by="District").to_crs(epsg=4326)
    return JSONResponse(content=district_polygon.__geo_interface__)


# ==========================================================
# Raster Metadata
# ==========================================================

@app.get("/info")
def raster_info():
    cog_path = require_cog()
    with rasterio.open(cog_path) as src:
        # src.bounds is in the raster's native CRS (often a projected CRS in
        # meters, e.g. UTM). It must be reprojected to EPSG:4326 before it's
        # usable as lon/lat bounds for Leaflet — otherwise the tile layer's
        # bounds are nonsensical and Leaflet silently requests zero tiles.
        if src.crs is not None and src.crs.to_epsg() != 4326:
            left, bottom, right, top = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        else:
            left, bottom, right, top = src.bounds

        return {
            "name": cog_path.name,
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "dtype": str(src.dtypes[0]),
            "nodata": src.nodata,
            "bounds_wgs84": [left, bottom, right, top],
            "center": [(left + right) / 2, (bottom + top) / 2],
            "min_zoom": 9,
            "max_zoom": 20,
            "tile_size": 256,
        }


# ==========================================================
# Pixel Inspector
# ==========================================================

@app.get("/pixel")
def pixel(lon: float, lat: float):
    cog_path = require_cog()
    with rasterio.open(cog_path) as src:
        try:
            row, col = src.index(lon, lat)
        except Exception:
            raise HTTPException(status_code=404, detail="Outside raster.")

        if row < 0 or row >= src.height or col < 0 or col >= src.width:
            raise HTTPException(status_code=404, detail="Outside raster.")

        value = int(src.read(1)[row, col])
        crop = CROP_LABELS.get(value, "Unknown")

        return {
            "longitude": lon,
            "latitude": lat,
            "row": int(row),
            "column": int(col),
            "pixel_value": value,
            "crop": crop,
        }


# ==========================================================
# XYZ Tile Server
# ==========================================================

@app.get("/tiles/{z}/{x}/{y}.png")
def tile(z: int, x: int, y: int):
    cog_path = require_cog()
    try:
        with COGReader(str(cog_path)) as cog:
            img = cog.tile(x, y, z)
            png = render(
                img.data,
                mask=img.mask,
                img_format="PNG",
                colormap=TILE_COLORMAP,
            )
    except Exception:
        # Outside raster extent / invalid tile -> return a fully transparent
        # 1x1 pixel instead of a 500, so Leaflet doesn't spam the console.
        png = render(
            np.zeros((1, 1, 1), dtype="uint8"),
            mask=np.zeros((1, 1), dtype="uint8"),
            img_format="PNG",
        )

    return Response(content=png, media_type="image/png")


# ==========================================================
# Village Statistics
# ==========================================================

@app.get("/village_stats")
def village_stats(village: str):
    gdf = require_village_gdf()
    cog_path = require_cog()

    subset = gdf[gdf["Vill_name"].str.upper() == village.upper()]
    if len(subset) == 0:
        raise HTTPException(status_code=404, detail="Village not found.")

    gdf_utm = subset.to_crs("EPSG:32643")
    village_area_ha = gdf_utm.geometry.area.sum() / 10000

    with rasterio.open(cog_path) as src:
        reproj = subset.to_crs(src.crs) if subset.crs != src.crs else subset
        geometry = [mapping(reproj.geometry.iloc[0])]
        # Use a fill value (255) that can never collide with real class codes
        # (0=NoData, 1=Cotton, 2=Paddy), so pixels outside the polygon but
        # inside its bounding box can be excluded from the stats entirely
        # instead of being miscounted as "NoData".
        clipped, _ = mask(src, geometry, crop=True, filled=True, nodata=255)
        band = clipped[0]

    cotton_pixels = int(np.sum(band == 1))
    paddy_pixels = int(np.sum(band == 2))
    nodata_pixels = int(np.sum(band == 0))
    outside_polygon_pixels = int(np.sum(band == 255))
    total_pixels = band.size
    polygon_pixels = cotton_pixels + paddy_pixels + nodata_pixels
    valid_pixels = cotton_pixels + paddy_pixels

    # Every pixel actually inside the polygon boundary gets its true share
    # of the area — Cotton, Paddy, and NoData all add up to the full
    # village area instead of NoData being an afterthought.
    if polygon_pixels > 0:
        cotton_area = village_area_ha * (cotton_pixels / polygon_pixels)
        paddy_area = village_area_ha * (paddy_pixels / polygon_pixels)
        other_area = village_area_ha * (nodata_pixels / polygon_pixels)
    else:
        cotton_area = 0
        paddy_area = 0
        other_area = village_area_ha

    def pct(part):
        return (part / village_area_ha * 100) if village_area_ha else 0

    return {
        "status": "success",
        "district": str(subset.iloc[0]["District"]),
        "village": str(subset.iloc[0]["Vill_name"]),
        "village_area_ha": round(float(village_area_ha), 2),
        "cotton_area_ha": round(cotton_area, 2),
        "paddy_area_ha": round(paddy_area, 2),
        "other_area_ha": round(other_area, 2),
        "cotton_percent": round(pct(cotton_area), 2),
        "paddy_percent": round(pct(paddy_area), 2),
        "other_percent": round(pct(other_area), 2),
        "cotton_pixels": cotton_pixels,
        "paddy_pixels": paddy_pixels,
        "nodata_pixels": nodata_pixels,
        "valid_pixels": valid_pixels,
        "total_pixels": total_pixels,
    }


# ==========================================================
# Search Village
# ==========================================================

@app.get("/search_village")
def search_village(query: str):
    gdf = require_village_gdf()
    query = query.upper().strip()

    result = gdf[gdf["Vill_name"].str.upper().str.contains(query, na=False)][
        ["District", "Vill_name"]
    ]

    villages = [
        {"district": row["District"], "village": row["Vill_name"]}
        for _, row in result.iterrows()
    ]

    return {"status": "success", "count": len(villages), "results": villages}


# ==========================================================
# Village Information
# ==========================================================

@app.get("/village_info")
def village_info(village: str):
    gdf = require_village_gdf()
    subset = gdf[gdf["Vill_name"].str.upper() == village.upper()]

    if len(subset) == 0:
        raise HTTPException(status_code=404, detail="Village not found.")

    row = subset.iloc[0]
    return {
        "status": "success",
        "state": row["STATE_UT"],
        "district": row["District"],
        "subdistrict": row["Sub_dist"],
        "village": row["Vill_name"],
        "village_lgd": row["Vill_LGD"],
        "district_lgd": row["Dist_LGD"],
    }


# ==========================================================
# District Summary
# ==========================================================

@app.get("/district_summary")
def district_summary(district: str):
    gdf = require_village_gdf()
    subset = gdf[gdf["District"].str.upper() == district.upper()]

    if len(subset) == 0:
        raise HTTPException(status_code=404, detail="District not found.")

    return {
        "status": "success",
        "district": district,
        "villages": len(subset),
        "subdistricts": int(subset["Sub_dist"].nunique()),
    }


# ==========================================================
# Health Check
# ==========================================================

@app.get("/health")
def health():
    return {
        "status": "OK" if not (state.village_db_error or state.cog_error) else "DEGRADED",
        "service": "GeoAgri AI",
        "version": "2.0",
        "village_db_loaded": state.village_gdf is not None,
        "village_db_error": state.village_db_error,
        "raster_available": state.cog_error is None,
        "raster_error": state.cog_error,
    }


# ==========================================================
# Available Layers
# ==========================================================

@app.get("/layers")
def layers():
    return {
        "layers": [
            "Crop Raster",
            "Village Boundary",
            "District Boundary",
            "OpenStreetMap",
            "Satellite",
        ]
    }


# ==========================================================
# Viewer Configuration
# ==========================================================

@app.get("/viewer_config")
def viewer_config():
    return {
        "title": "GeoAgri AI",
        "default_district": "SIRSA",
        "default_zoom": 10,
        "enable_pixel_inspector": True,
        "enable_measure_tool": True,
        "enable_draw_tool": True,
        "enable_export": True,
    }
