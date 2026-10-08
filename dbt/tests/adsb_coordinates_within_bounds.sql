select flight_id, event_ts, longitude, latitude
from {{ ref('fact_adsb_observations') }}
where longitude < -180 or longitude > 180
   or latitude < -90 or latitude > 90
