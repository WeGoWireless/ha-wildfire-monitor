# Wildfire Monitor for Home Assistant

Wildfire Monitor combines **NASA FIRMS**, **NOAA NESDIS Next Generation Fire System (NGFS)**, and **NIFC WFIGS/IRWIN** data to provide an incident-level wildfire monitoring view in Home Assistant.

Rather than relying on a single source, Wildfire Monitor combines three complementary views of wildfire activity:

- **NIFC WFIGS/IRWIN** — reported wildfire incidents, names, acreage, containment, cause, discovery information, and incident-management metadata
- **NOAA NGFS** — rapid geostationary satellite fire detection and tracking
- **NASA FIRMS** — VIIRS/MODIS thermal detections and fire radiative power

This allows Wildfire Monitor to represent a known wildfire even when no satellite currently detects heat, while adding NGFS and FIRMS thermal evidence when it becomes available.

The integration keeps the underlying detection information available while also grouping and associating observations into probable wildfire incidents for dashboards, monitoring, and alerts.

> Wildfire Monitor is a fork and extension of `bangboomben/ha-nasa-firms`.
> The original MIT license and copyright notice are retained in `LICENSE`.

---

## Highlights

- NASA FIRMS VIIRS/MODIS thermal fire detections
- NOAA NGFS / GOES rapid fire detections and tracking
- NIFC WFIGS/IRWIN reported wildfire incidents
- Combined WFIGS + NGFS + FIRMS incident view
- Reported wildfire names even when no current satellite heat is detected
- Reported acreage and containment information
- Fire cause and discovery information when available
- Protecting agency and incident-management metadata
- Multiple NGFS tracking features can be combined into one incident
- FIRMS hotspot clustering into probable incidents
- Nearest fire and nearest named wildfire sensors
- Configurable monitoring radius and separate alert radius
- New-fire Home Assistant events for automation and notifications
- Wind-at-fire and wind-based smoke-direction analysis
- Regional fire-wind threat sensors
- Automatic seasonal monitoring with reduced off-season polling
- Configurable polling intervals
- Predicted VIIRS satellite observation times
- Independent feed handling so a temporary source failure does not erase healthy data from other sources
- Last-successful WFIGS and NGFS data retained during temporary feed failures
- FIRMS truncation detection and Home Assistant Repair warning
- Ignore zones and persistent heat-source filtering inherited from the original integration

---

## What's new in wm15

Version `0.9.0-wm.15` adds **NIFC WFIGS/IRWIN** as a third wildfire data source.

This is an important addition because a known wildfire may not have a current satellite thermal detection.

Wildfire Monitor can now continue to show a reported incident from WFIGS while independently determining whether FIRMS or NGFS currently sees thermal activity associated with it.

wm15 also adds:

- WFIGS incident monitoring
- WFIGS feed diagnostics
- Reported acreage
- Percent contained
- Fire cause
- Discovery information
- Protecting agency/unit information
- Incident-management information
- Cross-source WFIGS / NGFS / FIRMS association
- Improved incident deduplication
- Spatial safeguards for matching incidents with the same name
- New generic wildfire event for WFIGS-backed incidents
- Improved handling of temporary NGFS and WFIGS feed failures
- Containment-aware new-fire alert handling

---

## Data sources

### NIFC WFIGS / IRWIN

WFIGS provides information about **known and reported wildfire incidents**.

Depending on the incident, Wildfire Monitor may expose information such as:

- Incident name
- Reported acres
- Discovery acres
- Percent contained
- Fire cause
- Discovery time
- Last WFIGS modification time
- IRWIN ID
- Unique fire identifier
- Protecting agency
- Protecting unit
- Incident management organization
- Personnel
- Nearby city/state information

WFIGS information describes a reported incident. It does **not** necessarily mean that satellite-detectable heat is currently present.

### NOAA NGFS

NOAA's Next Generation Fire System provides rapid geostationary satellite fire detection and tracking.

Wildfire Monitor uses NGFS for:

- Rapid thermal detection
- Fire tracking features
- Detection counts
- Incident names when supplied
- Fire radiative power when available
- Rapid new-fire awareness

NGFS is treated as an experimental data source by the integration.

### NASA FIRMS

NASA FIRMS provides satellite thermal detections from instruments including VIIRS and MODIS.

Wildfire Monitor uses FIRMS for:

- Thermal hotspot detections
- Fire radiative power (FRP)
- Hotspot clustering
- Incident association
- Wind-at-fire analysis
- Home Assistant `geo_location` entities
- VIIRS observation scheduling

A NASA FIRMS MAP_KEY is required.

---

## Reported incidents vs. satellite heat

A reported wildfire does not always have a current satellite detection.

Wildfire Monitor uses WFIGS/IRWIN to retain awareness of known wildfire incidents even when FIRMS or NGFS currently reports no thermal activity.

When satellite detections are associated with the same incident, Wildfire Monitor combines the sources.

An incident may therefore appear as:

- `WFIGS`
- `NGFS`
- `FIRMS`
- `WFIGS + NGFS`
- `WFIGS + FIRMS`
- `NGFS + FIRMS`
- `WFIGS + NGFS + FIRMS`

For example, a WFIGS-only incident can remain visible with its reported acreage and containment while showing that there is **no current FIRMS/NGFS heat detected**.

If NGFS or FIRMS subsequently detects thermal activity associated with that incident, the combined incident can reflect the additional source.

A WFIGS-only incident should therefore not automatically be interpreted as an actively burning fire with current satellite-detectable heat.

---

## Installation with HACS as a custom repository

> **Important:** Do not install Wildfire Monitor and the original `ha-nasa-firms` integration at the same time.
>
> Wildfire Monitor intentionally retains the internal Home Assistant domain `nasa_firms` for compatibility, so both integrations use the same `custom_components/nasa_firms` directory.

1. In Home Assistant, open **HACS**.
2. Open the **three-dot menu** and choose **Custom repositories**.
3. Add the Wildfire Monitor GitHub repository:

   `https://github.com/WeGoWireless/ha-wildfire-monitor`

4. Select **Integration** as the repository type.
5. Add the repository.
6. Open **Wildfire Monitor** in HACS.
7. Choose **Download**.
8. Restart Home Assistant.
9. Go to **Settings → Devices & services → Add integration**.
10. Search for **Wildfire Monitor**.

Requires Home Assistant **2025.6.0** or newer.

---

## Manual installation

Copy:

`custom_components/nasa_firms`

into:

`config/custom_components/`

Then restart Home Assistant.

The internal Home Assistant domain remains `nasa_firms` for compatibility with installations migrated from the original integration.

---

## Configuration

You will need a free **NASA FIRMS MAP_KEY**.

Obtain a MAP_KEY from NASA FIRMS, then add Wildfire Monitor from:

**Settings → Devices & services → Add integration**

Search for:

**Wildfire Monitor**

The configuration flow includes options for:

- Monitored location
- Monitoring radius
- Alert radius
- FIRMS satellite selection
- Detection filters
- Seasonal monitoring behavior
- Polling intervals
- Ignore zones

---

## Monitoring radius vs. alert radius

The two radii serve different purposes.

### Monitoring radius

The monitoring radius controls the larger region analyzed by Wildfire Monitor.

It is used for regional wildfire awareness, incident association, and fire-wind analysis.

### Alert radius

The alert radius identifies incidents close enough to be considered inside your local area of concern.

This allows a relatively large area to be monitored while keeping a smaller radius for local alerts.

For example, you might monitor fires across a broad region while only generating high-priority notifications for incidents much closer to the monitored location.

---

## Seasonal monitoring

Wildfire Monitor supports seasonal monitoring modes so aggressive polling does not need to continue throughout the entire year.

Available behavior includes:

- **Automatic seasonal**
- **Full**
- **Reduced**
- **Disabled**

With **Automatic seasonal** monitoring, Wildfire Monitor uses full monitoring during the configured wildfire season and reduced polling outside that season.

The default wildfire season is:

**May 1 through October 31**

Reduced mode continues monitoring while lowering request frequency.

This is useful for maintaining off-season wildfire awareness without polling every source at peak-season frequency.

---

## Incident model

Wildfire data sources describe different aspects of a fire.

A satellite detection is not necessarily a separate wildfire, and a reported wildfire may have no current satellite detection.

Wildfire Monitor therefore maintains several layers of information.

### 1. Raw thermal detections

Raw observations from:

- NASA FIRMS
- NOAA NGFS

### 2. Detection groups

Wildfire Monitor groups related observations into:

- FIRMS hotspot clusters
- NGFS tracking features

### 3. Incident groups

Related FIRMS detections can be grouped into probable incidents.

Multiple nearby NGFS tracking features associated with the same named incident can also be represented as one incident.

### 4. Reported WFIGS incidents

WFIGS supplies known wildfire incidents independently of the satellite feeds.

These incidents may include names, acreage, containment, cause, and incident-management information.

### 5. Combined incidents

Wildfire Monitor conservatively associates WFIGS, NGFS, and FIRMS information when the available evidence indicates they represent the same wildfire.

Geographic proximity remains an important matching constraint.

Cross-source matching intentionally favors avoiding incorrect incident merges over aggressively combining every nearby detection.

Incident association is heuristic and should not be interpreted as an official fire perimeter or identity determination.

---

## Useful sensors

Entity IDs depend on the configured integration entry and monitored location.

Important sensors include:

### Nearby wildfires

Probable wildfire incident count with a compact incident list.

May contain incidents originating from WFIGS, NGFS, FIRMS, or combinations of those sources.

### Named wildfires

Named incidents sorted by distance.

Names may originate from WFIGS or NGFS.

### Nearest combined fire

The closest combined wildfire representation.

Useful attributes can include:

- Source
- Incident name
- Distance
- Direction
- Bearing
- Alert-radius status
- FIRMS detection count
- NGFS detection count
- Maximum FRP
- WFIGS reported acres
- Percent contained
- Fire cause
- IRWIN information
- Wind information

This is particularly useful for dashboards and proximity-alert automations.

### Nearest combined incident

The closest incident-level representation after cross-source association.

### Nearest named wildfire

The closest incident with an available wildfire name.

### Nearest NGFS smoke threat

The closest wind-monitored NGFS fire whose calculated fire-wind relationship is directed toward the monitored location.

> This is a **wind-based smoke-direction estimate**, not an observed or forecast smoke plume.

### Next satellite observation

Predicted next VIIRS observation opportunity.

### WFIGS incidents

Provides WFIGS feed and incident diagnostics, including the number of records received and incidents within the monitoring radius.

Raw FIRMS and NGFS diagnostic sensors remain available for troubleshooting and detailed dashboards.

---

## Fire wind and smoke-direction analysis

Wildfire Monitor can compare wind at a detected fire with the direction from the fire toward the monitored location.

This provides useful situational awareness such as whether fire winds are generally:

- Toward the monitored location
- Crosswind
- Away from the monitored location

This should **not** be interpreted as an actual smoke-plume observation or smoke forecast.

Atmospheric transport is more complicated than a simple surface-wind vector.

The current feature is best considered **fire-wind / smoke-direction awareness**.

---

## New-fire events

Wildfire Monitor exposes Home Assistant events that can be used for automations and notifications.

### `wildfire_monitor_new_fire`

Generated for a newly observed combined wildfire incident meeting the integration's alert criteria.

This supports WFIGS-backed incident awareness and can include information such as:

- Incident name
- Distance
- Direction
- Bearing
- Source
- Reported acreage
- Percent contained
- Fire cause
- FIRMS detection count
- NGFS detection count

A fully contained WFIGS-only incident with no current FIRMS or NGFS thermal detections is retained for situational awareness without being treated as a new active-fire alert.

### `wildfire_monitor_new_ngfs_fire`

Generated when a previously unseen NGFS tracking feature first appears inside the configured alert radius during the current Home Assistant runtime.

The first successful NGFS refresh after Home Assistant starts establishes the initial baseline and does not generate alerts for every already-existing NGFS feature.

This event can be useful for rapid notification when new satellite thermal activity appears.

---

## Example new-fire automation

The following is intentionally generic. Replace the notification service with your own Home Assistant notification target.

```yaml
alias: Wildfire Monitor New Fire
triggers:
  - trigger: event
    event_type: wildfire_monitor_new_fire

actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "🔥 New wildfire reported"
      message: >
        {{ trigger.event.data.name or 'Wildfire' }}
        · {{ trigger.event.data.distance_miles }} mi
        {{ trigger.event.data.direction or '' }}
        · {{ trigger.event.data.source or 'Unknown source' }}

mode: queued
