select distinct
    flight_date as date_key,
    cast(extract(year from flight_date) as integer) as year,
    cast(extract(quarter from flight_date) as integer) as quarter,
    cast(extract(month from flight_date) as integer) as month,
    {{ month_label('flight_date') }} as month_name,
    cast({{ iso_day_of_week('flight_date') }} as integer) as day_of_week,
    {{ weekday_label('flight_date') }} as day_name
from {{ ref('stg_bts_flights') }}
