select flight_id, origin_airport_code, destination_airport_code
from {{ ref('fact_flights') }}
where origin_airport_code !~ '^[A-Z0-9]{3}$'
   or destination_airport_code !~ '^[A-Z0-9]{3}$'
