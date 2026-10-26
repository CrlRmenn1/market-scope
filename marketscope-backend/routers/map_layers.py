"""Map layer routes: admin CRUD for hazard/zoning layers, plus the public active-layer feed."""
from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from core.security import verify_admin_token
from models.requests import AdminMapLayerCreateRequest, AdminMapLayerUpdateRequest
from services.map_layers import (
    MAX_IMPORT_BYTES,
    MapLayerError,
    MapLayerNotFound,
    create_map_layer,
    delete_map_layer,
    get_active_map_layer,
    get_map_layer,
    get_map_layer_file,
    import_map_layer,
    list_map_layers,
    set_map_layer_active,
    update_map_layer,
)
from services.osm_data import get_reference_map_json


router = APIRouter()


def _run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except MapLayerError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MapLayerNotFound:
        raise HTTPException(status_code=404, detail="Map layer not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/map-layers/reference")
def public_reference_map():
    """Roads and waterways from the local OpenStreetMap file, for the admin map editor's plain road view."""
    data = _run(get_reference_map_json)
    if data is None:
        raise HTTPException(status_code=503, detail="The road map data (panabo.pbf) is not available on the server.")
    return Response(content=data, media_type="application/json", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/map-layers/active")
def public_active_map_layer(category: str):
    layer = _run(get_active_map_layer, category)
    if not layer:
        return {"status": "success", "layer": None, "geojson": None}
    geojson = layer.pop("geojson")
    return {"status": "success", "layer": layer, "geojson": geojson}


@router.get("/admin/map-layers")
def admin_list_map_layers(category: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    return {"status": "success", "layers": _run(list_map_layers, category)}


@router.get("/admin/map-layers/{layer_id}")
def admin_get_map_layer(layer_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    return {"status": "success", "layer": _run(get_map_layer, layer_id)}


@router.post("/admin/map-layers")
def admin_create_map_layer(payload: AdminMapLayerCreateRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    layer = _run(create_map_layer, payload.category, payload.name, payload.source_note, payload.geojson, activate=payload.activate)
    return {"status": "success", "layer": layer}


@router.post("/admin/map-layers/import")
async def admin_import_map_layer(
    file: UploadFile = File(...),
    category: str = Form(...),
    name: str = Form(""),
    source_note: str = Form(""),
    x_admin_token: str | None = Header(default=None),
):
    verify_admin_token(x_admin_token)
    data = await file.read(MAX_IMPORT_BYTES + 1)
    layer = await run_in_threadpool(
        _run, import_map_layer, category, name, source_note, file.filename, file.content_type, data
    )
    return {"status": "success", "layer": layer}


@router.put("/admin/map-layers/{layer_id}")
def admin_update_map_layer(layer_id: int, payload: AdminMapLayerUpdateRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    layer = _run(update_map_layer, layer_id, payload.name, payload.source_note, payload.geojson)
    return {"status": "success", "layer": layer}


@router.post("/admin/map-layers/{layer_id}/activate")
def admin_activate_map_layer(layer_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    return {"status": "success", "layer": _run(set_map_layer_active, layer_id, True)}


@router.post("/admin/map-layers/{layer_id}/deactivate")
def admin_deactivate_map_layer(layer_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    return {"status": "success", "layer": _run(set_map_layer_active, layer_id, False)}


@router.delete("/admin/map-layers/{layer_id}")
def admin_delete_map_layer(layer_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    return {"status": "success", "deleted_map_layer_id": _run(delete_map_layer, layer_id)}


@router.get("/admin/map-layers/{layer_id}/files/{file_id}")
def admin_download_map_layer_file(layer_id: int, file_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    found = _run(get_map_layer_file, layer_id, file_id)
    filename = found["filename"].replace('"', "")
    return Response(
        content=bytes(found["data"]),
        media_type=found["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
