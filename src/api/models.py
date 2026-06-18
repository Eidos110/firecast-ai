from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from src.database import get_engine, Session, ModelVersion
from src.models.registry import (
    get_model_versions,
    get_active_model_version,
    activate_model_version,
    register_model_version,
)
from src.auth import get_api_key

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/")
async def list_models(api_key: str = Depends(get_api_key)):
    """
    List all models and their versions.
    Requires authentication.
    """
    engine = get_engine()
    if engine is None:
        return {"models": {}, "count": 0, "status": "unavailable"}

    try:
        with Session(engine) as db:
            stmt = select(ModelVersion.model_name).distinct()
            results = db.exec(stmt).all()
            model_names = [r for r in results]

            response = {}
            for name in model_names:
                response[name] = get_model_versions(name)

            return {"models": response, "count": sum(len(v) for v in response.values())}
    except Exception as e:
        return {"models": {}, "count": 0, "status": "error", "message": str(e)}


@router.get("/{model_name}")
async def list_model_versions(model_name: str, api_key: str = Depends(get_api_key)):
    """
    List versions for a specific model.
    Requires authentication.
    """
    versions = get_model_versions(model_name)
    return {"model": model_name, "versions": versions, "count": len(versions)}


@router.get("/{model_name}/active")
async def get_active_version(model_name: str, api_key: str = Depends(get_api_key)):
    """
    Get currently active version for a model.
    Requires authentication.
    """
    version = get_active_model_version(model_name)
    if version is None:
        raise HTTPException(status_code=404, detail="Active version not found")
    return version


@router.post("/{model_name}/activate")
async def activate_version(
    model_name: str, 
    version: str, 
    api_key: str = Depends(get_api_key)
):
    """
    Activate a specific version for a model.
    Requires authentication.
    """
    success = activate_model_version(model_name, version)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to activate version")
    return {"status": "success", "model": model_name, "version": version}


@router.post("/register")
async def register_model(
    model_name: str,
    version: str,
    file_path: str,
    metadata: Optional[dict] = None,
    performance_metrics: Optional[dict] = None,
    api_key: str = Depends(get_api_key),
):
    """
    Register a new model version.
    Requires authentication.
    """
    success = register_model_version(
        model_name=model_name,
        version=version,
        file_path=file_path,
        metadata=metadata,
        performance_metrics=performance_metrics,
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to register model")
    return {"status": "success", "model": model_name, "version": version}
