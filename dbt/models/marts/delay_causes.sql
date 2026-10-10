with delay_rows as (
    select flight_date, airline_id, airline_code, origin_airport_code, destination_airport_code,
           'carrier' as delay_cause, carrier_delay_minutes as delay_minutes from {{ ref('fact_flights') }}
    union all
    select flight_date, airline_id, airline_code, origin_airport_code, destination_airport_code,
           'weather', weather_delay_minutes from {{ ref('fact_flights') }}
    union all
    select flight_date, airline_id, airline_code, origin_airport_code, destination_airport_code,
           'nas', nas_delay_minutes from {{ ref('fact_flights') }}
    union all
    select flight_date, airline_id, airline_code, origin_airport_code, destination_airport_code,
           'security', security_delay_minutes from {{ ref('fact_flights') }}
    union all
    select flight_date, airline_id, airline_code, origin_airport_code, destination_airport_code,
           'late_aircraft', late_aircraft_delay_minutes from {{ ref('fact_flights') }}
)
select
    flight_date,
    airline_id,
    airline_code,
    origin_airport_code,
    destination_airport_code,
    delay_cause,
    sum(case when delay_minutes is not null then 1 else 0 end) as flights_with_cause,
    sum(delay_minutes) as total_delay_minutes,
    avg(delay_minutes) as average_delay_minutes
from delay_rows
where delay_minutes is not null
group by 1, 2, 3, 4, 5, 6
