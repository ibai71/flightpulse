select
    flight_id,
    icao24,
    callsign,
    icao_type,
    operator_name,
    start_airport_ident,
    end_airport_ident,
    event_ts::timestamp as event_ts,
    event_epoch::bigint as event_epoch,
    longitude::double precision as longitude,
    latitude::double precision as latitude,
    altitude_ft::double precision as altitude_ft,
    track_deg::double precision as track_deg,
    ground_speed_knots::double precision as ground_speed_knots,
    vertical_rate_fpm::double precision as vertical_rate_fpm,
    indicated_airspeed_knots::double precision as indicated_airspeed_knots,
    height_agl_ft::double precision as height_agl_ft
from {{ source('ingestion', 'adsb_observations') }}
