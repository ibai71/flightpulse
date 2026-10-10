select
    flight_id,
    icao24,
    callsign,
    icao_type,
    operator_name,
    start_airport_ident,
    end_airport_ident,
    cast(event_ts as timestamp) as event_ts,
    cast(event_epoch as bigint) as event_epoch,
    cast(longitude as double precision) as longitude,
    cast(latitude as double precision) as latitude,
    cast(altitude_ft as double precision) as altitude_ft,
    cast(track_deg as double precision) as track_deg,
    cast(ground_speed_knots as double precision) as ground_speed_knots,
    cast(vertical_rate_fpm as double precision) as vertical_rate_fpm,
    cast(indicated_airspeed_knots as double precision) as indicated_airspeed_knots,
    cast(height_agl_ft as double precision) as height_agl_ft
from {{ source('ingestion', 'adsb_observations') }}
