"""Admin routes to download one admin page's data as a JSON backup and upload it back."""
import datetime
import json

from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from core.security import verify_admin_token
from services.data_backup import BACKUP_DATASETS, MAX_BACKUP_BYTES, DataBackupError, export_dataset, import_dataset


router = APIRouter()


def _check_dataset(dataset: str):
    if dataset not in BACKUP_DATASETS:
        raise HTTPException(status_code=404, detail=f"Unknown dataset {dataset!r}")


def _run(action, *args):
    try:
        return action(*args)
    except DataBackupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/backup/{dataset}")
def admin_download_backup(dataset: str, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    _check_dataset(dataset)
    backup = _run(export_dataset, dataset)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=json.dumps(backup),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="marketscope-{dataset}-{stamp}.json"'},
    )


@router.post("/admin/backup/{dataset}")
async def admin_upload_backup(dataset: str, file: UploadFile = File(...), x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    _check_dataset(dataset)
    data = await file.read(MAX_BACKUP_BYTES + 1)
    if len(data) > MAX_BACKUP_BYTES:
        raise HTTPException(status_code=400, detail=f"The file is larger than {MAX_BACKUP_BYTES // (1024 * 1024)} MB.")
    try:
        payload = json.loads(data)
    except ValueError:
        raise HTTPException(status_code=400, detail="The file is not valid JSON.")
    summary = await run_in_threadpool(_run, import_dataset, dataset, payload)
    return {"status": "success", "summary": summary}
