select distinct on (flight_id, event_ts)
    flight_id,
    icao24,
    callsign,
    icao_type,
    operator_name,
    start_airport_ident,
    end_airport_ident,
    event_ts,
    event_epoch,
    longitude,
    latitude,
    altitude_ft,
    track_deg,
    ground_speed_knots,
    vertical_rate_fpm,
    indicated_airspeed_knots,
    height_agl_ft
from {{ ref('stg_adsb_observations') }}
order by flight_id, event_ts
