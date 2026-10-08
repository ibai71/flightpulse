select distinct
    flight_date as date_key,
    extract(year from flight_date)::integer as year,
    extract(quarter from flight_date)::integer as quarter,
    extract(month from flight_date)::integer as month,
    to_char(flight_date, 'Month') as month_name,
    extract(isodow from flight_date)::integer as day_of_week,
    to_char(flight_date, 'Day') as day_name
from {{ ref('stg_bts_flights') }}
