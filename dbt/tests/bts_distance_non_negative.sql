select flight_id, distance_miles
from {{ ref('fact_flights') }}
where distance_miles < 0
