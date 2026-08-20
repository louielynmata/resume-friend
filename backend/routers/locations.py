from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..schemas import (
    LocationListResponse,
    LocationNormalizeRequest,
    LocationNormalizeResponse,
)
from ..services.location_service import (
    CATALOG_FILENAME,
    LocationCatalog,
    LocationCatalogError,
)

router = APIRouter(prefix="/api/locations", tags=["locations"])


def get_location_catalog() -> LocationCatalog:
    return LocationCatalog(settings.model_files_path / CATALOG_FILENAME)


def _catalog_error(exc: LocationCatalogError) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={
            "code": "LOCATION_CATALOG_INVALID",
            "message": str(exc),
            "hint": (
                "Repair the JSON file or move it aside so Resume Friend can recreate "
                "the Remote seed."
            ),
            "status_code": 500,
        },
    )


@router.get("", response_model=LocationListResponse)
def list_locations(
    catalog: LocationCatalog = Depends(get_location_catalog),
) -> LocationListResponse:
    try:
        return LocationListResponse(locations=catalog.list_locations())
    except LocationCatalogError as exc:
        raise _catalog_error(exc) from exc


@router.post("/normalize", response_model=LocationNormalizeResponse)
def normalize_location(
    request: LocationNormalizeRequest,
    catalog: LocationCatalog = Depends(get_location_catalog),
) -> LocationNormalizeResponse:
    try:
        result = catalog.normalize(request.location, persist=request.persist)
        return LocationNormalizeResponse(
            raw=result.raw,
            normalized=result.normalized,
            added=result.added,
            locations=result.locations,
        )
    except LocationCatalogError as exc:
        raise _catalog_error(exc) from exc
