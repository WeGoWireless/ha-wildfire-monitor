"""Constants for the NASA FIRMS integration."""
from datetime import timedelta

DOMAIN = "nasa_firms"
CONF_MAP_KEY="map_key"; CONF_REGION="region"; CONF_SATELLITES="satellites"; CONF_WINDOW="window"
CONF_MIN_CONFIDENCE="min_confidence"; CONF_MIN_FRP="min_frp"; CONF_IGNORE_ZONES="ignore_zones"
CONF_WIND_FIRES="wind_fires"; CONF_AUTO_IGNORE="auto_ignore"; CONF_MONITORING_MODE="monitoring_mode"
CONF_FIRE_SEASON_START_MONTH="fire_season_start_month"; CONF_FIRE_SEASON_START_DAY="fire_season_start_day"
CONF_FIRE_SEASON_END_MONTH="fire_season_end_month"; CONF_FIRE_SEASON_END_DAY="fire_season_end_day"
CONF_FIRMS_FULL_INTERVAL_MIN="firms_full_interval_min"; CONF_NGFS_FULL_INTERVAL_MIN="ngfs_full_interval_min"
CONF_FIRMS_REDUCED_INTERVAL_MIN="firms_reduced_interval_min"; CONF_NGFS_REDUCED_INTERVAL_MIN="ngfs_reduced_interval_min"
CONF_ALERT_RADIUS="alert_radius"
DEFAULT_ZONE_RADIUS_M=1_000; MAX_ZONE_RADIUS_M=20_000
DEFAULT_SATELLITES=["noaa20","noaa21","snpp"]; DEFAULT_RADIUS_M=100_000; DEFAULT_ALERT_RADIUS_M=96_560
MAX_RADIUS_M=500_000; DEFAULT_MIN_CONFIDENCE="any"; DEFAULT_MIN_FRP=0.0; DEFAULT_AUTO_IGNORE=False
SOURCES_STORAGE_VERSION=1; SOURCES_STORAGE_KEY=f"{DOMAIN}.sources"
DEFAULT_WIND_FIRES=3; MAX_WIND_FIRES=5
MONITORING_AUTO="automatic"; MONITORING_FULL="full"; MONITORING_REDUCED="reduced"; MONITORING_DISABLED="disabled"
DEFAULT_MONITORING_MODE=MONITORING_AUTO
DEFAULT_FIRE_SEASON_START_MONTH=5; DEFAULT_FIRE_SEASON_START_DAY=1
DEFAULT_FIRE_SEASON_END_MONTH=10; DEFAULT_FIRE_SEASON_END_DAY=31
DEFAULT_FIRMS_FULL_INTERVAL_MIN=15; DEFAULT_NGFS_FULL_INTERVAL_MIN=5
DEFAULT_FIRMS_REDUCED_INTERVAL_MIN=120; DEFAULT_NGFS_REDUCED_INTERVAL_MIN=60
UPDATE_INTERVAL=timedelta(minutes=DEFAULT_FIRMS_FULL_INTERVAL_MIN)
REDUCED_UPDATE_INTERVAL=timedelta(minutes=DEFAULT_FIRMS_REDUCED_INTERVAL_MIN)
NGFS_UPDATE_INTERVAL=timedelta(minutes=DEFAULT_NGFS_FULL_INTERVAL_MIN)
NGFS_REDUCED_UPDATE_INTERVAL=timedelta(minutes=DEFAULT_NGFS_REDUCED_INTERVAL_MIN)
NGFS_LOOKBACK=timedelta(hours=2); NGFS_FETCH_COUNT=1000
NGFS_COLLECTION_WEST="ngfs_schema.ngfs_detections_scene_west_conus"
NGFS_COLLECTION_EAST="ngfs_schema.ngfs_detections_scene_east_conus"
NGFS_API_ROOT="https://fire.data.nesdis.noaa.gov/api/ogc/detections"
CLUSTER_RADIUS_KM=1.0; FETCH_COUNT=1000
GEO_SOURCE="nasa_firms"; ATTRIBUTION="Data courtesy of NASA FIRMS"
ATTRIBUTION_WEATHER="Wind data from MET Norway (CC BY 4.0, creativecommons.org/licenses/by/4.0/)"
ATTRIBUTION_PLACES="Place names from GeoNames (CC BY 4.0, creativecommons.org/licenses/by/4.0/)"
DATA_PLACES="places"
USER_AGENT="ha-nasa-firms/{version} github.com/bangboomben/ha-nasa-firms"
MAP_KEY_URL="https://firms.modaps.eosdis.nasa.gov/api/map_key/"
EVENT_NEW_NGFS_FIRE="wildfire_monitor_new_ngfs_fire"
EVENT_NEW_WILDFIRE="wildfire_monitor_new_fire"
