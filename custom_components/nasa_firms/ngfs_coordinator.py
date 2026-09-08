"""Independent NOAA NGFS update coordinator."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import WeatherError, WindObservation, bearing_deg, cardinal, haversine_km
from .const import (CONF_ALERT_RADIUS, DEFAULT_ALERT_RADIUS_M, CONF_NGFS_FULL_INTERVAL_MIN, CONF_NGFS_REDUCED_INTERVAL_MIN, DEFAULT_NGFS_FULL_INTERVAL_MIN, DEFAULT_NGFS_REDUCED_INTERVAL_MIN, MONITORING_DISABLED, MONITORING_REDUCED, NGFS_COLLECTION_EAST,
    NGFS_COLLECTION_WEST, NGFS_LOOKBACK, NGFS_REDUCED_UPDATE_INTERVAL, NGFS_UPDATE_INTERVAL, EVENT_NEW_NGFS_FIRE, EVENT_NEW_WILDFIRE)
from .ngfs import NgfsClient, NgfsDetection, NgfsError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NgfsTrackedFire:
    tracking_id: str
    name: str | None
    distance_km: float
    latest: datetime
    max_frp: float | None
    detection_count: int
    latitude: float
    longitude: float
    satellite: str | None
    bearing: float
    direction: str

@dataclass(frozen=True)
class CombinedIncident:
    """Conservative cross-feed view of one nearby wildfire incident."""
    incident_id: str
    source: str
    name: str | None
    distance_km: float
    latitude: float
    longitude: float
    latest: datetime | None
    max_frp: float | None
    firms_cluster_id: str | None = None
    ngfs_tracking_id: str | None = None
    ngfs_tracking_ids: tuple[str, ...] = ()
    ngfs_tracking_features: int = 0
    firms_detections: int = 0
    ngfs_detections: int = 0
    match_distance_km: float | None = None
    wfigs_irwin_id: str | None = None
    wfigs_unique_fire_identifier: str | None = None
    reported_acres: float | None = None
    discovery_acres: float | None = None
    percent_contained: float | None = None
    fire_cause: str | None = None
    fire_cause_general: str | None = None
    discovery_time: datetime | None = None
    wfigs_modified_time: datetime | None = None
    protecting_agency: str | None = None
    protecting_unit: str | None = None
    management_organization: str | None = None
    personnel: int | None = None
    city: str | None = None
    state: str | None = None


def _firms_datetime(value: str | None) -> datetime | None:
    """Parse the timestamp shape used by FIRMS clusters."""
    if not value:
        return None
    text = value.strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# Cross-feed matching is deliberately conservative. FIRMS pixels and NGFS
# tracked features can sit a few kilometres apart on the same fire front, but
# unrelated fires should not be merged merely because they share a region.
INCIDENT_MATCH_DISTANCE_KM = 5.0
# An exact WFIGS/NGFS incident-name match is stronger evidence than proximity
# alone, so allow a wider gate for large fires whose WFIGS point of origin can
# be well behind the active thermal front. Still require geographic plausibility
# so unrelated incidents with the same generic name cannot merge across a region.
WFIGS_NAME_MATCH_DISTANCE_KM = 25.0
INCIDENT_MATCH_TIME = timedelta(hours=24)
FIRMS_INCIDENT_GROUP_DISTANCE_KM = 5.0


@dataclass
class NgfsData:
    detections: list[NgfsDetection] = field(default_factory=list)
    monitoring_active: bool = True
    error: str | None = None
    records_received: int = 0
    records_in_radius: int = 0
    collection: str | None = None
    last_successful_update: datetime | None = None
    query_lookback_minutes: int = 0
    records_with_valid_coordinates: int = 0
    nearest_raw_distance_km: float | None = None
    nearest_raw_latitude: float | None = None
    nearest_raw_longitude: float | None = None
    tracked_fires: list[NgfsTrackedFire] = field(default_factory=list)
    # Wind keyed by NGFS feature_tracking_id. The lookup budget is shared with
    # the FIRMS wind setting (normally 3, hard-capped at 5) so a busy NGFS
    # scene cannot turn the 5-minute fire poll into dozens of met.no calls.
    tracked_wind: dict[str, WindObservation] = field(default_factory=dict)
    # Compatibility shortcut used by the wm7/wm8 entities.
    nearest_tracked_wind: WindObservation | None = None
    combined_incidents: list[CombinedIncident] = field(default_factory=list)
    matched_incidents: int = 0
    # Fires that entered the configured alert radius for the first time during
    # this Home Assistant runtime. Empty on the initial baseline refresh.
    new_alert_fires: list[NgfsTrackedFire] = field(default_factory=list)
    # Newly seen combined incidents inside the alert radius. The first
    # successful refresh establishes a baseline, so HA restarts do not
    # announce already-known WFIGS/FIRMS/NGFS incidents as new fires.
    new_alert_incidents: list[CombinedIncident] = field(default_factory=list)

    @property
    def nearest(self) -> NgfsDetection | None:
        return self.detections[0] if self.detections else None
    @property
    def latest(self) -> datetime | None:
        return max((d.acquired for d in self.detections), default=None)
    @property
    def max_frp(self) -> float | None:
        values=[d.frp for d in self.detections if d.frp is not None]
        return max(values) if values else None

class NgfsCoordinator(DataUpdateCoordinator[NgfsData]):
    """Poll NGFS independently so FIRMS keeps its own 15-minute cadence."""
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: NgfsClient, firms) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"ngfs {entry.title}", update_interval=NGFS_UPDATE_INTERVAL)
        self.client=client; self.firms=firms
        self.latitude=firms.latitude; self.longitude=firms.longitude; self.radius_km=firms.radius_km; self._bbox=firms._bbox
        cfg={**entry.data, **entry.options}
        self.alert_radius_km=float(cfg.get(CONF_ALERT_RADIUS, DEFAULT_ALERT_RADIUS_M)) / 1000
        self.full_interval_min=int(cfg.get(CONF_NGFS_FULL_INTERVAL_MIN, DEFAULT_NGFS_FULL_INTERVAL_MIN))
        self.reduced_interval_min=int(cfg.get(CONF_NGFS_REDUCED_INTERVAL_MIN, DEFAULT_NGFS_REDUCED_INTERVAL_MIN))
        # None means the first successful NGFS refresh has not established a
        # baseline yet. Keep IDs for the whole runtime so a temporary feed gap
        # does not create a duplicate "new fire" alert when a feature returns.
        self._seen_alert_tracking_ids: set[str] | None = None
        # Incident-level alert identities. WFIGS IRWIN/UniqueFireIdentifier
        # are preferred because they remain stable as thermal feeds join.
        self._seen_alert_incident_ids: set[str] | None = None

    @staticmethod
    def _alert_incident_aliases(incident: CombinedIncident) -> set[str]:
        """All known identities for one incident, used for cross-feed dedup."""
        aliases: set[str] = set()

        if incident.wfigs_irwin_id:
            aliases.add(f"irwin:{incident.wfigs_irwin_id.strip().casefold()}")

        if incident.wfigs_unique_fire_identifier:
            aliases.add(
                f"ufi:{incident.wfigs_unique_fire_identifier.strip().casefold()}"
            )

        for tracking_id in incident.ngfs_tracking_ids:
            aliases.add(f"ngfs:{tracking_id}")

        if incident.ngfs_tracking_id:
            aliases.add(f"ngfs:{incident.ngfs_tracking_id}")

        if incident.firms_cluster_id:
            aliases.add(f"firms:{incident.firms_cluster_id}")

        if not aliases:
            aliases.add(incident.incident_id)

        return aliases

    @staticmethod
    def _alert_source(incident: CombinedIncident) -> str:
        """Human-readable source for notifications."""
        if incident.source == "WFIGS":
            return "WFIGS/IRWIN"
        return incident.source

    def _collection(self) -> str:
        # GOES-West is preferred west of the central CONUS overlap; East otherwise.
        return NGFS_COLLECTION_WEST if self.longitude < -100 else NGFS_COLLECTION_EAST

    async def _async_update_data(self) -> NgfsData:
        mode=self.firms._effective_monitoring_mode()
        if mode == MONITORING_DISABLED:
            self.update_interval=None
            return NgfsData(monitoring_active=False)
        self.update_interval = timedelta(minutes=self.reduced_interval_min if mode == MONITORING_REDUCED else self.full_interval_min)
        try:
            found=await self.client.fetch(self._collection(), self._bbox, NGFS_LOOKBACK)
        except NgfsError as err:
            _LOGGER.warning(
                "NGFS fetch failed; retaining last-good NGFS/combined data; "
                "FIRMS and WFIGS are unaffected: %s",
                err,
            )

            previous = self.data
            if (
                isinstance(previous, NgfsData)
                and previous.last_successful_update is not None
            ):
                return NgfsData(
                    detections=list(previous.detections),
                    monitoring_active=True,
                    error=str(err),
                    records_received=previous.records_received,
                    records_in_radius=previous.records_in_radius,
                    collection=self._collection(),
                    last_successful_update=previous.last_successful_update,
                    query_lookback_minutes=int(
                        NGFS_LOOKBACK.total_seconds() / 60
                    ),
                    records_with_valid_coordinates=(
                        previous.records_with_valid_coordinates
                    ),
                    nearest_raw_distance_km=previous.nearest_raw_distance_km,
                    nearest_raw_latitude=previous.nearest_raw_latitude,
                    nearest_raw_longitude=previous.nearest_raw_longitude,
                    tracked_fires=list(previous.tracked_fires),
                    tracked_wind=dict(previous.tracked_wind),
                    nearest_tracked_wind=previous.nearest_tracked_wind,
                    combined_incidents=list(previous.combined_incidents),
                    matched_incidents=previous.matched_incidents,
                    # A failed refresh cannot establish a genuinely new fire.
                    new_alert_fires=[],
                    new_alert_incidents=[],
                )

            return NgfsData(
                error=str(err),
                collection=self._collection(),
                query_lookback_minutes=int(
                    NGFS_LOOKBACK.total_seconds() / 60
                ),
            )
        nearby=[]
        raw_distances=[]
        for d in found:
            distance=haversine_km(self.latitude,self.longitude,d.latitude,d.longitude)
            raw_distances.append((distance,d))
            if distance <= self.radius_km:
                nearby.append((distance,d))
        nearby.sort(key=lambda item:item[0])
        raw_distances.sort(key=lambda item:item[0])
        nearest_raw = raw_distances[0] if raw_distances else None

        # NGFS assigns a stable feature_tracking_id to repeated observations of
        # the same tracked fire feature. Collapse the rapid GOES detections into
        # one useful fire summary per tracking id. Detections without an id stay
        # available in the raw sensors but are not mislabeled as tracked fires.
        groups = {}
        for distance, d in nearby:
            if not d.feature_tracking_id:
                continue
            groups.setdefault(d.feature_tracking_id, []).append((distance, d))
        tracked = []
        for tracking_id, items in groups.items():
            closest_distance, closest = min(items, key=lambda item: item[0])
            latest_detection = max((d for _, d in items), key=lambda d: d.acquired)
            frps = [d.frp for _, d in items if d.frp is not None]
            name = next((d.known_incident_name for _, d in items if d.known_incident_name), None)
            fire_bearing = bearing_deg(self.latitude, self.longitude, closest.latitude, closest.longitude)
            tracked.append(NgfsTrackedFire(
                tracking_id=tracking_id, name=name, distance_km=closest_distance,
                latest=latest_detection.acquired, max_frp=max(frps) if frps else None,
                detection_count=len(items), latitude=closest.latitude, longitude=closest.longitude,
                satellite=latest_detection.satellite, bearing=fire_bearing,
                direction=cardinal(fire_bearing),
            ))
        tracked.sort(key=lambda fire: fire.distance_km)

        # Wind/smoke analysis for the nearest tracked NGFS fires. Reuse the
        # integration's existing wind-fire budget (normally 3, max 5). This is
        # deliberately sequential for the same reason as FIRMS wind lookups:
        # met.no is supplemental and should never be hammered by a busy scene.
        # A single failure ends this cycle's weather work but never invalidates
        # NGFS fire data.
        tracked_wind: dict[str, WindObservation] = {}
        for fire in tracked[: self.firms.wind_fires]:
            try:
                wind = await self.firms.weather.wind_at(fire.latitude, fire.longitude)
            except WeatherError as err:
                _LOGGER.debug("NGFS tracked-fire wind unavailable: %s", err)
                break
            if wind is not None:
                tracked_wind[fire.tracking_id] = wind

        nearest_wind = (
            tracked_wind.get(tracked[0].tracking_id) if tracked else None
        )
        combined_incidents, matched_incidents = self._combined_incidents(tracked)

        # Early-warning layer: a tracking feature becomes "new nearby" the
        # first time it is observed inside the user's alert radius. The first
        # successful refresh after startup only establishes a baseline, which
        # prevents Home Assistant restarts from generating false ignition alerts.
        alert_fires = [f for f in tracked if f.distance_km <= self.alert_radius_km]
        current_alert_ids = {f.tracking_id for f in alert_fires}
        if self._seen_alert_tracking_ids is None:
            new_alert_fires: list[NgfsTrackedFire] = []
            self._seen_alert_tracking_ids = set(current_alert_ids)
        else:
            new_alert_fires = [
                f for f in alert_fires
                if f.tracking_id not in self._seen_alert_tracking_ids
            ]
            self._seen_alert_tracking_ids.update(current_alert_ids)

        for fire in new_alert_fires:
            self.hass.bus.async_fire(
                EVENT_NEW_NGFS_FIRE,
                {
                    "entry_id": self.config_entry.entry_id,
                    "tracking_id": fire.tracking_id,
                    "name": fire.name,
                    "distance_miles": round(fire.distance_km * 0.621371, 1),
                    "direction": fire.direction,
                    "bearing": round(fire.bearing),
                    "latest": fire.latest.isoformat(),
                    "max_frp": fire.max_frp,
                    "detection_count": fire.detection_count,
                    "satellite": fire.satellite,
                    "alert_radius_miles": round(self.alert_radius_km * 0.621371, 1),
                },
            )

        # Cross-feed new-fire layer. The first successful combined refresh is
        # baseline only, preventing HA restarts from announcing existing fires.
        alert_incidents = [
            i for i in combined_incidents
            if i.distance_km <= self.alert_radius_km
        ]
        current_incident_aliases = [
            (incident, self._alert_incident_aliases(incident))
            for incident in alert_incidents
        ]

        if self._seen_alert_incident_ids is None:
            new_alert_incidents: list[CombinedIncident] = []
            self._seen_alert_incident_ids = {
                alias
                for _, aliases in current_incident_aliases
                for alias in aliases
            }
        else:
            new_alert_incidents = []
            for incident, aliases in current_incident_aliases:
                # Any overlapping alias means this physical incident has already
                # been announced. This prevents NGFS-first -> WFIGS-later or
                # WFIGS-first -> NGFS/FIRMS-later duplicate new-fire alerts.
                if self._seen_alert_incident_ids.isdisjoint(aliases):
                    new_alert_incidents.append(incident)

                # Always learn every alias now known for the incident so future
                # source associations continue to collapse to the same alert.
                self._seen_alert_incident_ids.update(aliases)

        for incident in new_alert_incidents:
            # NGFS-only fires already generate the legacy wm14 event above.
            # This first wm15 step adds WFIGS-backed reported-fire alerts.
            if "WFIGS" not in incident.source:
                continue

            # Keep fully-contained WFIGS-only historical records visible, but
            # do not announce them as newly active without current thermal heat.
            fully_contained = (
                incident.percent_contained is not None
                and incident.percent_contained >= 100
            )
            has_thermal_heat = (
                incident.firms_detections > 0
                or incident.ngfs_detections > 0
            )
            if fully_contained and not has_thermal_heat:
                continue

            incident_bearing = bearing_deg(
                self.latitude,
                self.longitude,
                incident.latitude,
                incident.longitude,
            )
            self.hass.bus.async_fire(
                EVENT_NEW_WILDFIRE,
                {
                    "entry_id": self.config_entry.entry_id,
                    "incident_id": incident.incident_id,
                    "irwin_id": incident.wfigs_irwin_id,
                    "unique_fire_identifier": incident.wfigs_unique_fire_identifier,
                    "name": incident.name,
                    "source": self._alert_source(incident),
                    "combined_source": incident.source,
                    "distance_miles": round(incident.distance_km * 0.621371, 1),
                    "direction": cardinal(incident_bearing),
                    "bearing": round(incident_bearing),
                    "reported_acres": incident.reported_acres,
                    "discovery_acres": incident.discovery_acres,
                    "percent_contained": incident.percent_contained,
                    "fire_cause": incident.fire_cause_general or incident.fire_cause,
                    "discovery_time": (
                        incident.discovery_time.isoformat()
                        if incident.discovery_time else None
                    ),
                    "latest": incident.latest.isoformat() if incident.latest else None,
                    "max_frp": incident.max_frp,
                    "firms_detections": incident.firms_detections,
                    "ngfs_detections": incident.ngfs_detections,
                    "alert_radius_miles": round(self.alert_radius_km * 0.621371, 1),
                },
            )

        return NgfsData(
            detections=[d for _,d in nearby],
            records_received=len(found),
            records_in_radius=len(nearby),
            collection=self._collection(),
            last_successful_update=datetime.now().astimezone(),
            query_lookback_minutes=int(NGFS_LOOKBACK.total_seconds()/60),
            records_with_valid_coordinates=len(raw_distances),
            nearest_raw_distance_km=nearest_raw[0] if nearest_raw else None,
            nearest_raw_latitude=nearest_raw[1].latitude if nearest_raw else None,
            nearest_raw_longitude=nearest_raw[1].longitude if nearest_raw else None,
            tracked_fires=tracked,
            tracked_wind=tracked_wind,
            nearest_tracked_wind=nearest_wind,
            combined_incidents=combined_incidents,
            matched_incidents=matched_incidents,
            new_alert_fires=new_alert_fires,
            new_alert_incidents=new_alert_incidents,
        )

    def _combined_incidents(self, tracked: list[NgfsTrackedFire]) -> tuple[list[CombinedIncident], int]:
        """Build conservative wildfire incidents from FIRMS and NGFS.

        wm12 first groups nearby FIRMS pixel-clusters into incident footprints,
        then groups multiple NGFS tracking features that carry the same incident
        name when those features are geographically connected within 5 km.
        Unnamed NGFS features remain independent. The resulting NGFS incident
        groups are associated with FIRMS incident groups when any member of each
        footprint is within 5 km and their observations are within 24 hours.

        This keeps NOAA's individual tracking IDs available while avoiding the
        assumption that one feature_tracking_id always equals one wildfire.
        """
        firms_clusters = list(self.firms.data.clusters)

        # Connected components over the existing 1 km FIRMS clusters. Using
        # member-to-member links preserves elongated fire fronts better than a
        # centroid-only merge while retaining a conservative 5 km local gate.
        remaining = set(range(len(firms_clusters)))
        groups: list[list[int]] = []
        while remaining:
            seed = min(remaining)
            remaining.remove(seed)
            group = [seed]
            queue = [seed]
            while queue:
                current = queue.pop()
                c = firms_clusters[current]
                linked = []
                for other in sorted(remaining):
                    o = firms_clusters[other]
                    if haversine_km(c.latitude, c.longitude, o.latitude, o.longitude) <= FIRMS_INCIDENT_GROUP_DISTANCE_KM:
                        linked.append(other)
                for other in linked:
                    remaining.remove(other)
                    group.append(other)
                    queue.append(other)
            groups.append(group)

        def firms_group_summary(indices: list[int]):
            members = [firms_clusters[i] for i in indices]
            representative = min(members, key=lambda f: f.distance_km)
            times = [(t, f) for f in members if (t := _firms_datetime(f.acq_datetime)) is not None]
            latest = max((t for t, _ in times), default=None)
            frps = [f.frp for f in members if f.frp is not None]
            return {
                "indices": indices,
                "members": members,
                "representative": representative,
                "latest": latest,
                "max_frp": max(frps) if frps else None,
                "detections": sum(f.detections for f in members),
            }

        firms_summaries = [firms_group_summary(g) for g in groups]

        # A named NGFS incident may have multiple feature_tracking_id values.
        # Group only same-named features that are connected within 5 km. This
        # merges examples like two nearby "Upper Smith" tracks without folding
        # unrelated same-name incidents together across a region. Unnamed tracks
        # intentionally remain one group per feature ID.
        ngfs_groups: list[list[int]] = []
        named_buckets: dict[str, list[int]] = {}
        for idx, fire in enumerate(tracked):
            if fire.name and fire.name.strip():
                named_buckets.setdefault(fire.name.strip().casefold(), []).append(idx)
            else:
                ngfs_groups.append([idx])

        for indices in named_buckets.values():
            remaining_named = set(indices)
            while remaining_named:
                seed = min(remaining_named)
                remaining_named.remove(seed)
                group = [seed]
                queue = [seed]
                while queue:
                    current = queue.pop()
                    c = tracked[current]
                    linked = []
                    for other in sorted(remaining_named):
                        o = tracked[other]
                        if haversine_km(c.latitude, c.longitude, o.latitude, o.longitude) <= INCIDENT_MATCH_DISTANCE_KM:
                            linked.append(other)
                    for other in linked:
                        remaining_named.remove(other)
                        group.append(other)
                        queue.append(other)
                ngfs_groups.append(group)

        def ngfs_group_summary(indices: list[int]):
            members = [tracked[i] for i in indices]
            representative = min(members, key=lambda f: f.distance_km)
            latest = max(f.latest for f in members)
            frps = [f.max_frp for f in members if f.max_frp is not None]
            names = [f.name for f in members if f.name]
            name = names[0] if names else None
            tracking_ids = tuple(f.tracking_id for f in members)
            return {
                "indices": indices,
                "members": members,
                "representative": representative,
                "latest": latest,
                "max_frp": max(frps) if frps else None,
                "detections": sum(f.detection_count for f in members),
                "name": name,
                "tracking_ids": tracking_ids,
            }

        ngfs_summaries = [ngfs_group_summary(g) for g in ngfs_groups]

        candidates: list[tuple[float, int, int]] = []
        for ni, ngfs_group in enumerate(ngfs_summaries):
            ngfs_time = ngfs_group["latest"]
            if ngfs_time.tzinfo is None:
                ngfs_time = ngfs_time.replace(tzinfo=timezone.utc)
            for gi, firms_group in enumerate(firms_summaries):
                # Match actual footprint members rather than centroids. This is
                # important for elongated fire fronts in both feeds.
                gap = min(
                    haversine_km(n.latitude, n.longitude, f.latitude, f.longitude)
                    for n in ngfs_group["members"]
                    for f in firms_group["members"]
                )
                if gap > INCIDENT_MATCH_DISTANCE_KM:
                    continue
                firms_time = firms_group["latest"]
                if firms_time is None or abs(ngfs_time - firms_time) > INCIDENT_MATCH_TIME:
                    continue
                candidates.append((gap, ni, gi))

        candidates.sort()
        used_ngfs: set[int] = set()
        used_firms: set[int] = set()
        matches: list[tuple[float, int, int]] = []
        for gap, ni, gi in candidates:
            if ni in used_ngfs or gi in used_firms:
                continue
            used_ngfs.add(ni)
            used_firms.add(gi)
            matches.append((gap, ni, gi))

        incidents: list[CombinedIncident] = []
        for gap, ni, gi in matches:
            n_group = ngfs_summaries[ni]
            f_group = firms_summaries[gi]
            n = n_group["representative"]
            f = f_group["representative"]
            ft = f_group["latest"]
            latest = max(n_group["latest"], ft) if ft else n_group["latest"]
            frps = [v for v in (n_group["max_frp"], f_group["max_frp"]) if v is not None]
            if f.distance_km <= n.distance_km:
                lat, lon, dist = f.latitude, f.longitude, f.distance_km
            else:
                lat, lon, dist = n.latitude, n.longitude, n.distance_km
            ids = n_group["tracking_ids"]
            incidents.append(CombinedIncident(
                incident_id=f"ngfs:{ids[0]}", source="FIRMS + NGFS", name=n_group["name"],
                distance_km=dist, latitude=lat, longitude=lon, latest=latest,
                max_frp=max(frps) if frps else None, firms_cluster_id=f.id,
                ngfs_tracking_id=ids[0], ngfs_tracking_ids=ids,
                ngfs_tracking_features=len(ids), firms_detections=f_group["detections"],
                ngfs_detections=n_group["detections"], match_distance_km=gap,
            ))

        for ni, n_group in enumerate(ngfs_summaries):
            if ni in used_ngfs:
                continue
            n = n_group["representative"]
            ids = n_group["tracking_ids"]
            incidents.append(CombinedIncident(
                incident_id=f"ngfs:{ids[0]}", source="NGFS", name=n_group["name"],
                distance_km=n.distance_km, latitude=n.latitude, longitude=n.longitude,
                latest=n_group["latest"], max_frp=n_group["max_frp"],
                ngfs_tracking_id=ids[0], ngfs_tracking_ids=ids,
                ngfs_tracking_features=len(ids), ngfs_detections=n_group["detections"],
            ))

        for gi, f_group in enumerate(firms_summaries):
            if gi in used_firms:
                continue
            f = f_group["representative"]
            incidents.append(CombinedIncident(
                incident_id=f"firms:{f.id}", source="FIRMS", name=None,
                distance_km=f.distance_km, latitude=f.latitude, longitude=f.longitude,
                latest=f_group["latest"], max_frp=f_group["max_frp"],
                firms_cluster_id=f.id, firms_detections=f_group["detections"],
            ))

        # WFIGS / IRWIN is the authoritative reported-incident layer. Merge it
        # after the thermal FIRMS/NGFS association so a reported wildfire can
        # exist with no current satellite heat, while a matching thermal fire
        # inherits the official incident name and incident metadata.
        wfigs = getattr(self.firms, "wfigs", None)
        wfigs_incidents = (
            list(wfigs.data.incidents)
            if wfigs is not None and wfigs.data is not None
            else []
        )

        def source_with_wfigs(source: str) -> str:
            parts = set(source.split(" + "))
            parts.add("WFIGS")
            return " + ".join(
                name for name in ("WFIGS", "NGFS", "FIRMS") if name in parts
            )

        for reported in wfigs_incidents:
            w = reported.incident
            w_name = w.name.strip().casefold() if w.name and w.name.strip() else None

            # Prefer an exact incident-name association when NGFS already carries
            # the WFIGS/IRWIN name, but still require geographic plausibility.
            # The wider name gate accommodates large fires where WFIGS reports a
            # point of origin while the thermal front has moved kilometres away.
            name_candidates = []
            for idx, incident in enumerate(incidents):
                if (
                    not w_name
                    or not incident.name
                    or incident.name.strip().casefold() != w_name
                ):
                    continue

                gap = haversine_km(
                    w.latitude,
                    w.longitude,
                    incident.latitude,
                    incident.longitude,
                )
                if gap <= WFIGS_NAME_MATCH_DISTANCE_KM:
                    name_candidates.append((gap, idx, incident))

            if name_candidates:
                wfigs_gap, match_idx, matched = min(
                    name_candidates, key=lambda item: item[0]
                )
            else:
                spatial_candidates = [
                    (
                        haversine_km(
                            w.latitude,
                            w.longitude,
                            incident.latitude,
                            incident.longitude,
                        ),
                        idx,
                        incident,
                    )
                    for idx, incident in enumerate(incidents)
                ]
                spatial_candidates = [
                    item
                    for item in spatial_candidates
                    if item[0] <= INCIDENT_MATCH_DISTANCE_KM
                ]
                if spatial_candidates:
                    wfigs_gap, match_idx, matched = min(
                        spatial_candidates, key=lambda item: item[0]
                    )
                else:
                    matched = None
                    match_idx = -1
                    wfigs_gap = None

            w_latest = w.modified_time or w.discovery_time

            if matched is None:
                incidents.append(
                    CombinedIncident(
                        incident_id=f"wfigs:{w.irwin_id or w.unique_fire_identifier or w.name or f'{w.latitude:.4f},{w.longitude:.4f}'}",
                        source="WFIGS",
                        name=w.name,
                        distance_km=reported.distance_km,
                        latitude=w.latitude,
                        longitude=w.longitude,
                        latest=w_latest,
                        max_frp=None,
                        wfigs_irwin_id=w.irwin_id,
                        wfigs_unique_fire_identifier=w.unique_fire_identifier,
                        reported_acres=w.acres,
                        discovery_acres=w.discovery_acres,
                        percent_contained=w.percent_contained,
                        fire_cause=w.fire_cause,
                        fire_cause_general=w.fire_cause_general,
                        discovery_time=w.discovery_time,
                        wfigs_modified_time=w.modified_time,
                        protecting_agency=w.protecting_agency,
                        protecting_unit=w.protecting_unit,
                        management_organization=w.management_organization,
                        personnel=w.personnel,
                        city=w.city,
                        state=w.state,
                    )
                )
                continue

            latest_values = [
                value for value in (matched.latest, w_latest) if value is not None
            ]
            latest = max(latest_values) if latest_values else None

            # Keep the closest representation for distance/ranking. WFIGS still
            # retains its own official point through its metadata/IRWIN identity.
            if reported.distance_km <= matched.distance_km:
                latitude = w.latitude
                longitude = w.longitude
                distance_km = reported.distance_km
            else:
                latitude = matched.latitude
                longitude = matched.longitude
                distance_km = matched.distance_km

            incidents[match_idx] = CombinedIncident(
                incident_id=matched.incident_id,
                source=source_with_wfigs(matched.source),
                name=w.name or matched.name,
                distance_km=distance_km,
                latitude=latitude,
                longitude=longitude,
                latest=latest,
                max_frp=matched.max_frp,
                firms_cluster_id=matched.firms_cluster_id,
                ngfs_tracking_id=matched.ngfs_tracking_id,
                ngfs_tracking_ids=matched.ngfs_tracking_ids,
                ngfs_tracking_features=matched.ngfs_tracking_features,
                firms_detections=matched.firms_detections,
                ngfs_detections=matched.ngfs_detections,
                match_distance_km=(
                    min(
                        value
                        for value in (matched.match_distance_km, wfigs_gap)
                        if value is not None
                    )
                    if matched.match_distance_km is not None or wfigs_gap is not None
                    else None
                ),
                wfigs_irwin_id=w.irwin_id,
                wfigs_unique_fire_identifier=w.unique_fire_identifier,
                reported_acres=w.acres,
                discovery_acres=w.discovery_acres,
                percent_contained=w.percent_contained,
                fire_cause=w.fire_cause,
                fire_cause_general=w.fire_cause_general,
                discovery_time=w.discovery_time,
                wfigs_modified_time=w.modified_time,
                protecting_agency=w.protecting_agency,
                protecting_unit=w.protecting_unit,
                management_organization=w.management_organization,
                personnel=w.personnel,
                city=w.city,
                state=w.state,
            )

        incidents.sort(key=lambda item: item.distance_km)
        return incidents, len(matches)

    def distance_km(self, detection: NgfsDetection | None) -> float | None:
        if detection is None: return None
        return haversine_km(self.latitude,self.longitude,detection.latitude,detection.longitude)
