"""Independent NIFC WFIGS / IRWIN update coordinator."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import bearing_deg, cardinal, haversine_km
from .const import MONITORING_DISABLED, MONITORING_REDUCED
from .wfigs import WfigsClient, WfigsError, WfigsIncident

_LOGGER = logging.getLogger(__name__)

# WFIGS itself updates frequently, but a 5-minute poll is plenty for reported
# incident information and keeps this feed independent of FIRMS and NGFS.
WFIGS_UPDATE_INTERVAL = timedelta(minutes=5)
WFIGS_REDUCED_UPDATE_INTERVAL = timedelta(hours=1)


@dataclass(frozen=True)
class WfigsNearbyIncident:
    """A WFIGS incident with location relative to Home Assistant."""

    incident: WfigsIncident
    distance_km: float
    bearing: float
    direction: str


@dataclass
class WfigsData:
    """Latest WFIGS coordinator data."""

    incidents: list[WfigsNearbyIncident] = field(default_factory=list)
    monitoring_active: bool = True
    error: str | None = None
    records_received: int = 0
    records_in_radius: int = 0
    last_successful_update: datetime | None = None

    @property
    def nearest(self) -> WfigsNearbyIncident | None:
        return self.incidents[0] if self.incidents else None


class WfigsCoordinator(DataUpdateCoordinator[WfigsData]):
    """Poll WFIGS independently of FIRMS and NGFS."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: WfigsClient,
        firms,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"wfigs {entry.title}",
            update_interval=WFIGS_UPDATE_INTERVAL,
        )

        self.client = client
        self.firms = firms

        self.latitude = firms.latitude
        self.longitude = firms.longitude
        self.radius_km = firms.radius_km
        self._bbox = firms._bbox

    async def _async_update_data(self) -> WfigsData:
        """Fetch and filter current WFIGS wildfire incidents."""

        mode = self.firms._effective_monitoring_mode()

        if mode == MONITORING_DISABLED:
            self.update_interval = None
            return WfigsData(monitoring_active=False)

        self.update_interval = (
            WFIGS_REDUCED_UPDATE_INTERVAL
            if mode == MONITORING_REDUCED
            else WFIGS_UPDATE_INTERVAL
        )

        try:
            found = await self.client.fetch(self._bbox)
        except WfigsError as err:
            _LOGGER.warning(
                "WFIGS fetch failed; FIRMS and NGFS are unaffected: %s",
                err,
            )

            # Keep the most recent successful WFIGS incident data through a
            # temporary API/network failure. The error remains visible so the
            # diagnostic sensor can clearly show that the retained data is stale.
            previous = self.data
            if (
                isinstance(previous, WfigsData)
                and previous.last_successful_update is not None
            ):
                return WfigsData(
                    incidents=list(previous.incidents),
                    monitoring_active=True,
                    error=str(err),
                    records_received=previous.records_received,
                    records_in_radius=previous.records_in_radius,
                    last_successful_update=previous.last_successful_update,
                )

            return WfigsData(error=str(err))

        nearby: list[WfigsNearbyIncident] = []

        for incident in found:
            distance = haversine_km(
                self.latitude,
                self.longitude,
                incident.latitude,
                incident.longitude,
            )

            if distance > self.radius_km:
                continue

            fire_bearing = bearing_deg(
                self.latitude,
                self.longitude,
                incident.latitude,
                incident.longitude,
            )

            nearby.append(
                WfigsNearbyIncident(
                    incident=incident,
                    distance_km=distance,
                    bearing=fire_bearing,
                    direction=cardinal(fire_bearing),
                )
            )

        nearby.sort(key=lambda item: item.distance_km)

        return WfigsData(
            incidents=nearby,
            records_received=len(found),
            records_in_radius=len(nearby),
            last_successful_update=datetime.now().astimezone(),
        )
