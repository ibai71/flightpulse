select flight_id, origin_airport_code, destination_airport_code
from {{ ref('fact_flights') }}
where not regexp_like(origin_airport_code, '^[A-Z0-9]{3}$')
   or not regexp_like(destination_airport_code, '^[A-Z0-9]{3}$')
