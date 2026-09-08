"""NIFC WFIGS / IRWIN current wildfire incident client."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientError, ClientSession


WFIGS_INCIDENTS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Incident_Locations_Current/FeatureServer/0/query"
)

# ArcGIS feature services commonly enforce a maximum record count per request.
# Page explicitly so a busy fire season cannot silently truncate the WFIGS
# incident list. 500 keeps responses modest while remaining efficient.
WFIGS_PAGE_SIZE = 500


class WfigsError(Exception):
    """WFIGS request or response failed."""


@dataclass(frozen=True)
class WfigsIncident:
    """Normalized WFIGS wildfire incident."""

    latitude: float
    longitude: float

    name: str | None = None
    incident_type: str | None = None

    acres: float | None = None
    discovery_acres: float | None = None
    percent_contained: float | None = None

    fire_cause: str | None = None
    fire_cause_general: str | None = None

    discovery_time: datetime | None = None
    modified_time: datetime | None = None

    irwin_id: str | None = None
    unique_fire_identifier: str | None = None

    protecting_agency: str | None = None
    protecting_unit: str | None = None
    management_organization: str | None = None

    personnel: int | None = None
    city: str | None = None
    state: str | None = None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _time(value: Any) -> datetime | None:
    """Convert ArcGIS epoch milliseconds or ISO timestamp to UTC datetime."""
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None

    text = str(value).strip()

    try:
        numeric = float(text)
        return datetime.fromtimestamp(numeric / 1000.0, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


class WfigsClient:
    """Read current wildfire incidents from NIFC WFIGS / IRWIN."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def fetch(
        self,
        bbox: tuple[float, float, float, float],
    ) -> list[WfigsIncident]:
        """Fetch active wildfire incidents within a bounding box."""

        lat_s, lon_w, lat_n, lon_e = bbox

        base_params = {
            "where": "IncidentTypeCategory='WF'",
            "geometry": f"{lon_w},{lat_s},{lon_e},{lat_n}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outSR": "4326",
            "returnGeometry": "true",
            "outFields": ",".join(
                (
                    "IncidentName",
                    "IncidentTypeCategory",
                    "IncidentSize",
                    "DiscoveryAcres",
                    "PercentContained",
                    "FireCause",
                    "FireCauseGeneral",
                    "FireDiscoveryDateTime",
                    "ModifiedOnDateTime_dt",
                    "IrwinID",
                    "UniqueFireIdentifier",
                    "POOProtectingAgency",
                    "POOProtectingUnit",
                    "IncidentManagementOrganization",
                    "TotalIncidentPersonnel",
                    "POOCity",
                    "POOState",
                    "InitialLatitude",
                    "InitialLongitude",
                )
            ),
            "orderByFields": "OBJECTID ASC",
            "resultRecordCount": str(WFIGS_PAGE_SIZE),
            "f": "json",
        }

        incidents: list[WfigsIncident] = []
        offset = 0

        while True:
            params = dict(base_params)
            params["resultOffset"] = str(offset)

            try:
                async with self._session.get(
                    WFIGS_INCIDENTS_URL,
                    params=params,
                    timeout=30,
                ) as response:
                    data = await response.json(content_type=None)

                    if response.status != 200:
                        raise WfigsError(
                            f"HTTP {response.status}: {str(data)[:200]}"
                        )

            except (ClientError, TimeoutError) as err:
                raise WfigsError(str(err)) from err
            except ValueError as err:
                raise WfigsError(f"Invalid JSON response: {err}") from err

            if not isinstance(data, dict):
                raise WfigsError("Unexpected WFIGS response")

            if "error" in data:
                error = data["error"]
                raise WfigsError(f"WFIGS API error: {error}")

            features = data.get("features", [])
            if not isinstance(features, list):
                raise WfigsError("Unexpected WFIGS features response")

            for feature in features:
                attrs = feature.get("attributes") or {}
                geometry = feature.get("geometry") or {}

                lat = _float(geometry.get("y"))
                lon = _float(geometry.get("x"))

                # Fall back to WFIGS initial coordinates if geometry is absent.
                if lat is None:
                    lat = _float(attrs.get("InitialLatitude"))
                if lon is None:
                    lon = _float(attrs.get("InitialLongitude"))

                if lat is None or lon is None:
                    continue

                incidents.append(
                    WfigsIncident(
                        latitude=lat,
                        longitude=lon,
                        name=_text(attrs.get("IncidentName")),
                        incident_type=_text(attrs.get("IncidentTypeCategory")),
                        acres=_float(attrs.get("IncidentSize")),
                        discovery_acres=_float(attrs.get("DiscoveryAcres")),
                        percent_contained=_float(attrs.get("PercentContained")),
                        fire_cause=_text(attrs.get("FireCause")),
                        fire_cause_general=_text(attrs.get("FireCauseGeneral")),
                        discovery_time=_time(attrs.get("FireDiscoveryDateTime")),
                        modified_time=_time(attrs.get("ModifiedOnDateTime_dt")),
                        irwin_id=_text(attrs.get("IrwinID")),
                        unique_fire_identifier=_text(
                            attrs.get("UniqueFireIdentifier")
                        ),
                        protecting_agency=_text(
                            attrs.get("POOProtectingAgency")
                        ),
                        protecting_unit=_text(
                            attrs.get("POOProtectingUnit")
                        ),
                        management_organization=_text(
                            attrs.get("IncidentManagementOrganization")
                        ),
                        personnel=_int(attrs.get("TotalIncidentPersonnel")),
                        city=_text(attrs.get("POOCity")),
                        state=_text(attrs.get("POOState")),
                    )
                )

            # ArcGIS sets exceededTransferLimit when more records are available.
            # Also continue when a full page is returned, because some services
            # omit that flag even though pagination is supported.
            exceeded = bool(data.get("exceededTransferLimit"))
            if not exceeded and len(features) < WFIGS_PAGE_SIZE:
                break

            if not features:
                break

            offset += len(features)

        return incidents
