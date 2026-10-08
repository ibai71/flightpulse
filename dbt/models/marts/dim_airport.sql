select airport_id, max(airport_code) as airport_code
from (
    select origin_airport_id as airport_id, origin_airport_code as airport_code
    from {{ ref('stg_bts_flights') }}
    union all
    select destination_airport_id, destination_airport_code
    from {{ ref('stg_bts_flights') }}
) airports
where airport_id is not null
group by airport_id
