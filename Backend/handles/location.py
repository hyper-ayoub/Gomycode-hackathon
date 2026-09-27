import math
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

FacilityType = Literal["pharmacy", "hospital", "clinic", "doctors"]


class Facility(BaseModel):
    name: str
    facility_type: str
    lat: float
    lon: float
    distance_km: float
    address: str | None = None


class NearbyFacilitiesResponse(BaseModel):
    query_lat: float
    query_lon: float
    radius_km: float
    results: list[Facility]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _format_address(tags: dict) -> str | None:
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


@router.get("/nearby", response_model=NearbyFacilitiesResponse, summary="Find nearby health facilities")
async def nearby_facilities(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_km: float = Query(3.0, gt=0, le=25, description="Search radius in km"),
    facility_type: FacilityType = Query("pharmacy", description="Type of facility to search for"),
    limit: int = Query(20, ge=1, le=100),
) -> NearbyFacilitiesResponse:
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="{facility_type}"](around:{radius_m},{lat},{lon});
      way["amenity"="{facility_type}"](around:{radius_m},{lat},{lon});
    );
    out center {limit};
    """

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": "DarijaDoc/0.1 (hackathon medical navigator)"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach location provider: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Location provider returned {response.status_code}")

    elements = response.json().get("elements", [])

    results: list[Facility] = []
    for el in elements:
        tags = el.get("tags", {})
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")
        if el_lat is None or el_lon is None:
            continue
        results.append(
            Facility(
                name=tags.get("name", "Unnamed facility"),
                facility_type=facility_type,
                lat=el_lat,
                lon=el_lon,
                distance_km=round(_haversine_km(lat, lon, el_lat, el_lon), 2),
                address=_format_address(tags),
            )
        )

    results.sort(key=lambda f: f.distance_km)

    return NearbyFacilitiesResponse(query_lat=lat, query_lon=lon, radius_km=radius_km, results=results[:limit])
