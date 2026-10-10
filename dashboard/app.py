from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "data" / "export"
SNAPSHOT_DIR = ROOT / "data" / "snapshot"
DEMO_DIR = ROOT / "data" / "demo"
SNAPSHOT_TABLES = ["airport_daily_performance", "airline_daily_performance", "delay_causes", "route_performance", "fact_adsb_observations", "airport_labels", "airline_labels", "aircraft_labels"]


def has_complete_snapshot(folder: Path) -> bool:
    return all((folder / f"{name}.csv").exists() for name in SNAPSHOT_TABLES)


DATA_DIR = EXPORT_DIR if has_complete_snapshot(EXPORT_DIR) else SNAPSHOT_DIR if has_complete_snapshot(SNAPSHOT_DIR) else DEMO_DIR

st.set_page_config(page_title="FlightPulse | Aviation Operations", page_icon=chr(0x2708), layout="wide")

COLORS = {"navy": "#10243A", "blue": "#277DA1", "teal": "#43AA8B", "orange": "#F8961E", "red": "#E76F51"}
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [COLORS["blue"], COLORS["teal"], COLORS["orange"], COLORS["red"], "#577590"]


@st.cache_data
def read_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for field in ("flight_date", "event_ts"):
        if field in frame:
            frame[field] = pd.to_datetime(frame[field], errors="coerce", utc=field == "event_ts")
    return frame


airport = read_csv("airport_daily_performance")
airline = read_csv("airline_daily_performance")
causes = read_csv("delay_causes")
routes = read_csv("route_performance")
adsb = read_csv("fact_adsb_observations")
airport_labels_frame = read_csv("airport_labels")
airline_labels_frame = read_csv("airline_labels")
aircraft_labels_frame = read_csv("aircraft_labels")
dataset_info_path = DATA_DIR / "dataset_info.json"
dataset_info = pd.read_json(dataset_info_path, typ="series") if dataset_info_path.exists() else pd.Series(dtype=object)
airport_name_lookup = dict(zip(airport_labels_frame.get("airport_code", []), airport_labels_frame.get("airport_name", [])))
airline_name_lookup = dict(zip(airline_labels_frame.get("airline_code", []), airline_labels_frame.get("airline_name", [])))
aircraft_name_lookup = dict(zip(aircraft_labels_frame.get("icao_type", []), aircraft_labels_frame.get("aircraft_name", [])))

if airport.empty or airline.empty:
    st.error("No hay datos de demo. Ejecuta `python scripts/create_demo_snapshot.py`.")
    st.stop()

is_demo = dataset_info.get("data_type", "synthetic_preview") == "synthetic_preview"

st.markdown("<div style='padding:8px 0 0;color:#277DA1;font-weight:700;letter-spacing:.12em'>AVIATION DATA | BATCH + STREAMING</div>", unsafe_allow_html=True)
st.title("FlightPulse")
st.caption("US flight operations, delays, cancellations, diversions, and aircraft trajectory observations.")
if is_demo:
    st.info("This is an illustrative sample with synthetic records. The production snapshot is built from BTS flight reports and an independent ADS-B trajectory sample.")

min_date = min(airport.flight_date.min(), airline.flight_date.min()).date()
max_date = max(airport.flight_date.max(), airline.flight_date.max()).date()
with st.sidebar:
    st.markdown("## FlightPulse")
    page = st.radio("Explore", ["Overview", "Airports", "Airlines", "Delay causes", "ADS-B"], label_visibility="collapsed")
    st.divider()
    selected_range = st.date_input("Flight date range", (min_date, max_date), min_value=min_date, max_value=max_date)
    st.caption("Source: BTS on-time performance and a separate ADS-B.aero trajectory sample.")

if isinstance(selected_range, tuple) and len(selected_range) == 2:
    start, end = pd.Timestamp(selected_range[0]), pd.Timestamp(selected_range[1])
else:
    start = end = pd.Timestamp(selected_range)

airport_period = airport[airport.flight_date.dt.date.between(start.date(), end.date())].copy()
airline_period = airline[airline.flight_date.dt.date.between(start.date(), end.date())].copy()
causes_period = causes[causes.flight_date.dt.date.between(start.date(), end.date())].copy() if not causes.empty else causes
routes_period = routes.copy()


def pct(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:.1%}"


def minutes(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:.1f} min"


def airport_display_name(code: object) -> str:
    if not isinstance(code, str) or not code.strip():
        return "Unknown airport"
    code = code.strip()
    lookup_code = code[1:] if code.startswith("K") and len(code) == 4 else code
    name = airport_name_lookup.get(lookup_code)
    return name if name else "Other airport"


CAUSE_NAMES = {
    "carrier": "Airline operations",
    "weather": "Weather",
    "nas": "National Airspace System",
    "security": "Security",
    "late_aircraft": "Aircraft arriving late",
}


if page == "Overview":
    st.subheader("Flight operations at a glance")
    if is_demo:
        st.markdown("FlightPulse demonstrates two data pipelines. The batch flow cleans and deduplicates monthly BTS on-time flight records with PySpark, writes Parquet layers, and publishes analytics models to PostgreSQL with dbt. A separate streaming flow replays ADS-B trajectory points through Kafka and validates them with Spark Structured Streaming. ADS-B observations remain independent from BTS flights.")
    else:
        flight_start = dataset_info.get("flight_date_start", min_date.isoformat())
        flight_end = dataset_info.get("flight_date_end", max_date.isoformat())
        flight_count = int(dataset_info.get("flight_rows", 0))
        adsb_count = int(dataset_info.get("adsb_observations", len(adsb)))
        adsb_date = dataset_info.get("adsb_date_utc", "the selected sample day")
        adsb_airport = airport_display_name(dataset_info.get("adsb_airport_requested", "KJFK"))
        st.markdown(f"BTS TranStats reports **{flight_count:,} scheduled flights** from {flight_start} to {flight_end}. PySpark cleans, types, and deduplicates the monthly files into Bronze/Silver Parquet; dbt builds analytics models in PostgreSQL. A separate ADS-B sample around **{adsb_airport} on {adsb_date}** contains **{adsb_count:,} observations**, replayed through Kafka and validated with Spark Structured Streaming. The sources are not matched together.")
    flights = int(airline_period.scheduled_flights.sum())
    denominator = airline_period.eligible_arrivals.sum()
    on_time = airline_period.on_time_arrivals.sum()
    weighted_otp = on_time / denominator if denominator else float("nan")
    known_delay = airline_period.average_arrival_delay_minutes.notna()
    delay_weight = airline_period.loc[known_delay, "eligible_arrivals"].sum()
    mean_delay = ((airline_period.loc[known_delay, "average_arrival_delay_minutes"] * airline_period.loc[known_delay, "eligible_arrivals"]).sum() / delay_weight) if delay_weight else float("nan")
    cancellation = airline_period.cancelled_flights.sum() / flights if flights else float("nan")
    diversion = airline_period.diverted_flights.sum() / flights if flights else float("nan")
    cards = st.columns(5)
    for col, label, value in zip(cards, ["Scheduled flights", "On-time arrivals", "Avg. arrival delay", "Cancellation rate", "Diversion rate"], [f"{flights:,}", pct(weighted_otp), minutes(mean_delay), pct(cancellation), pct(diversion)]):
        col.metric(label, value)

    trend = airline_period.groupby("flight_date", as_index=False).agg(scheduled_flights=("scheduled_flights", "sum"), eligible_arrivals=("eligible_arrivals", "sum"), on_time_arrivals=("on_time_arrivals", "sum"), average_arrival_delay_minutes=("average_arrival_delay_minutes", "mean"))
    trend["on_time_rate"] = trend.on_time_arrivals / trend.eligible_arrivals.replace(0, pd.NA)
    left, right = st.columns([1.6, 1])
    with left:
        st.plotly_chart(px.line(trend, x="flight_date", y="on_time_rate", markers=True, labels={"flight_date": "Date", "on_time_rate": "On-time arrival rate"}, title="Arrival punctuality over time").update_yaxes(tickformat=".0%"), width="stretch")
    with right:
        carrier_volume = airline_period.groupby("airline_code", as_index=False).scheduled_flights.sum()
        carrier_volume["airline_name"] = carrier_volume.airline_code.map(airline_name_lookup).fillna("Other airline")
        st.plotly_chart(px.bar(carrier_volume.sort_values("scheduled_flights", ascending=False), x="airline_name", y="scheduled_flights", labels={"airline_name": "Airline", "scheduled_flights": "Flights"}, title="Flights by airline"), width="stretch")
    st.caption("On-time arrival = arrival delay below 15 minutes among non-cancelled, non-diverted flights with a known arrival delay. Early arrivals count as on time; unknown values remain excluded.")

elif page == "Airports":
    st.subheader("Airport performance")
    role = st.selectbox("Airport role", ["destination", "origin"], format_func=lambda x: "Arrivals" if x == "destination" else "Departures")
    view = airport_period[airport_period.airport_role == role]
    view = view.assign(delay_total=view.average_delay_minutes * view.eligible_flights)
    ranking = view.groupby("airport_code", as_index=False).agg(scheduled_flights=("scheduled_flights", "sum"), eligible_flights=("eligible_flights", "sum"), on_time_flights=("on_time_flights", "sum"), delay_total=("delay_total", "sum"), cancelled_flights=("cancelled_flights", "sum"), diverted_flights=("diverted_flights", "sum"))
    ranking["average_delay_minutes"] = ranking.delay_total / ranking.eligible_flights.replace(0, pd.NA)
    ranking = ranking.drop(columns="delay_total")
    ranking["on_time_rate"] = ranking.on_time_flights / ranking.eligible_flights.replace(0, pd.NA)
    ranking["airport_name"] = ranking.airport_code.map(airport_name_lookup).fillna("Other location")
    ranking["airport_label"] = ranking.airport_name
    search = st.text_input("Search airport", placeholder="City or airport code, e.g. Los Angeles or LAX").strip().casefold()
    if search:
        ranking = ranking[ranking.airport_name.str.casefold().str.contains(search, na=False, regex=False) | ranking.airport_code.str.casefold().str.contains(search, na=False, regex=False)]
    if ranking.empty:
        st.warning("No airports match that search in the selected dates.")
        st.stop()
    st.caption(f"{len(ranking):,} airports match the current selection. The table includes every match.")
    first, second = st.columns(2)
    with first:
        st.plotly_chart(px.bar(ranking.nlargest(15, "scheduled_flights"), x="airport_label", y="scheduled_flights", title="Busiest matching airports", labels={"airport_label": "Airport", "scheduled_flights": "Flights"}), width="stretch")
    with second:
        st.plotly_chart(px.scatter(ranking, x="scheduled_flights", y="average_delay_minutes", size="scheduled_flights", color="on_time_rate", hover_name="airport_label", title="Volume vs average delay", labels={"scheduled_flights": "Flights", "average_delay_minutes": "Average delay (min)", "on_time_rate": "On-time rate"}), width="stretch")
    airport_table = ranking[["airport_name", "scheduled_flights", "average_delay_minutes", "on_time_rate", "cancelled_flights", "diverted_flights"]].rename(columns={"airport_name": "Airport", "scheduled_flights": "Scheduled flights", "average_delay_minutes": "Average delay (min)", "on_time_rate": "On-time arrivals", "cancelled_flights": "Cancellations", "diverted_flights": "Diversions"})
    st.dataframe(airport_table.sort_values("Scheduled flights", ascending=False).style.format({"On-time arrivals": "{:.1%}", "Average delay (min)": "{:.1f}"}), width="stretch", hide_index=True)

elif page == "Airlines":
    st.subheader("Airline performance")
    airline_view = airline_period.assign(delay_total=airline_period.average_arrival_delay_minutes * airline_period.eligible_arrivals)
    ranking = airline_view.groupby(["airline_code"], as_index=False).agg(scheduled_flights=("scheduled_flights", "sum"), eligible_arrivals=("eligible_arrivals", "sum"), on_time_arrivals=("on_time_arrivals", "sum"), delay_total=("delay_total", "sum"), cancelled_flights=("cancelled_flights", "sum"), diverted_flights=("diverted_flights", "sum"))
    ranking["average_arrival_delay_minutes"] = ranking.delay_total / ranking.eligible_arrivals.replace(0, pd.NA)
    ranking = ranking.drop(columns="delay_total")
    ranking["on_time_rate"] = ranking.on_time_arrivals / ranking.eligible_arrivals.replace(0, pd.NA)
    ranking["airline_name"] = ranking.airline_code.map(airline_name_lookup).fillna("Other airline")
    search = st.text_input("Search airline", placeholder="Airline name, e.g. Delta or Southwest").strip().casefold()
    if search:
        ranking = ranking[ranking.airline_name.str.casefold().str.contains(search, na=False, regex=False) | ranking.airline_code.str.casefold().str.contains(search, na=False, regex=False)]
    if ranking.empty:
        st.warning("No airlines match that search in the selected dates.")
        st.stop()
    st.caption(f"{len(ranking):,} airlines match the current selection.")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.bar(ranking.sort_values("on_time_rate"), x="airline_name", y="on_time_rate", color="on_time_rate", title="Arrival punctuality by airline", labels={"airline_name": "Airline", "on_time_rate": "On-time rate"}).update_yaxes(tickformat=".0%"), width="stretch")
    with c2:
        st.plotly_chart(px.scatter(ranking, x="scheduled_flights", y="average_arrival_delay_minutes", size="scheduled_flights", color="on_time_rate", hover_name="airline_name", title="Scale vs average arrival delay", labels={"scheduled_flights": "Flights", "average_arrival_delay_minutes": "Average delay (min)"}), width="stretch")
    airline_table = ranking[["airline_name", "scheduled_flights", "average_arrival_delay_minutes", "on_time_rate", "cancelled_flights", "diverted_flights"]].rename(columns={"airline_name": "Airline", "scheduled_flights": "Scheduled flights", "average_arrival_delay_minutes": "Average arrival delay (min)", "on_time_rate": "On-time arrivals", "cancelled_flights": "Cancellations", "diverted_flights": "Diversions"})
    st.dataframe(airline_table.sort_values("Scheduled flights", ascending=False).style.format({"On-time arrivals": "{:.1%}", "Average arrival delay (min)": "{:.1f}"}), width="stretch", hide_index=True)

elif page == "Delay causes":
    st.subheader("Reported delay causes")
    if causes_period.empty:
        st.warning("No cause-level delay data in this sample.")
    else:
        summary = causes_period.groupby("delay_cause", as_index=False).agg(total_delay_minutes=("total_delay_minutes", "sum"), flights_with_cause=("flights_with_cause", "sum"))
        summary["cause_name"] = summary.delay_cause.map(CAUSE_NAMES).fillna("Other delay cause")
        summary["total_delay_hours"] = summary.total_delay_minutes / 60
        c1, c2 = st.columns([1, 1.4])
        with c1:
            st.plotly_chart(px.pie(summary, names="cause_name", values="total_delay_minutes", hole=.55, title="Share of reported delay minutes"), width="stretch")
        with c2:
            daily = causes_period.groupby(["flight_date", "delay_cause"], as_index=False).total_delay_minutes.sum()
            daily["cause_name"] = daily.delay_cause.map(CAUSE_NAMES).fillna("Other delay cause")
            st.plotly_chart(px.area(daily, x="flight_date", y="total_delay_minutes", color="cause_name", title="Reported delay minutes over time", labels={"flight_date": "Date", "total_delay_minutes": "Delay minutes", "cause_name": "Cause"}), width="stretch")
        cause_table = summary[["cause_name", "flights_with_cause", "total_delay_minutes", "total_delay_hours"]].rename(columns={"cause_name": "Delay cause", "flights_with_cause": "Flights with reported cause", "total_delay_minutes": "Delay minutes", "total_delay_hours": "Delay hours"})
        st.dataframe(cause_table.sort_values("Delay minutes", ascending=False).style.format({"Delay minutes": "{:,.0f}", "Delay hours": "{:,.1f}", "Flights with reported cause": "{:,.0f}"}), width="stretch", hide_index=True)
        if not routes_period.empty:
            st.markdown("#### Routes with the highest average arrival delay (full snapshot)")
            route_table = routes_period.copy()
            route_table["Origin"] = route_table.origin_airport_code.map(airport_display_name)
            route_table["Destination"] = route_table.destination_airport_code.map(airport_display_name)
            route_table = route_table[["Origin", "Destination", "scheduled_flights", "average_arrival_delay_minutes", "on_time_rate"]].rename(columns={"scheduled_flights": "Scheduled flights", "average_arrival_delay_minutes": "Average arrival delay (min)", "on_time_rate": "On-time arrivals"})
            st.dataframe(route_table.sort_values("Average arrival delay (min)", ascending=False).head(15).style.format({"Average arrival delay (min)": "{:.1f}", "On-time arrivals": "{:.1%}"}), width="stretch", hide_index=True)
    st.caption("Cause-specific fields are independently reported by BTS; null causes are not treated as zero and cause totals may not equal total flight delay.")

else:
    st.subheader("ADS-B trajectory explorer")
    if adsb.empty:
        st.info("No ADS-B observations in this snapshot. Run the ADS-B replay and export again.")
    else:
        flights = sorted(adsb.flight_id.dropna().unique())
        def flight_label(flight_id: str) -> str:
            sample = adsb[adsb.flight_id == flight_id].iloc[0]
            origin_code = sample.get("start_airport_ident")
            destination_code = sample.get("end_airport_ident")
            origin = airport_display_name(origin_code) if isinstance(origin_code, str) and origin_code.strip() else None
            destination = airport_display_name(destination_code) if isinstance(destination_code, str) and destination_code.strip() else None
            if origin and destination:
                route = f"{origin} to {destination}"
            elif origin:
                route = f"Track departing {origin}"
            elif destination:
                route = f"Track arriving at {destination}"
            else:
                route = "Aircraft track"
            return f"{route} | Sample {flights.index(flight_id) + 1}"

        flight_id = st.selectbox("Select a flight", flights, format_func=flight_label)
        path = adsb[adsb.flight_id == flight_id].sort_values("event_ts")
        meta = path.iloc[0]
        aircraft_name = aircraft_name_lookup.get(meta.get("icao_type"), "Aircraft model unavailable")
        operator = meta.get("operator_name")
        operator = operator.title() if isinstance(operator, str) and operator.strip() else "Unknown"
        st.caption(f"Aircraft: {aircraft_name} | Operator: {operator}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Track points", f"{len(path):,}")
        m2.metric("Peak altitude", f"{path.altitude_ft.max():,.0f} ft" if path.altitude_ft.notna().any() else "-")
        m3.metric("Peak ground speed", f"{path.ground_speed_knots.max():,.0f} kt" if path.ground_speed_knots.notna().any() else "-")
        st.plotly_chart(px.scatter_map(path, lat="latitude", lon="longitude", color="altitude_ft", hover_data=["event_ts", "ground_speed_knots", "altitude_ft"], zoom=3, height=520, title="Timestamped ADS-B positions", map_style="open-street-map", labels={"altitude_ft": "Altitude (ft)"}), width="stretch")
        altitude_chart, speed_chart = st.columns(2)
        with altitude_chart:
            st.plotly_chart(px.line(path, x="event_ts", y="altitude_ft", title="Altitude over time", labels={"event_ts": "UTC time", "altitude_ft": "Altitude (ft)"}), width="stretch")
        with speed_chart:
            st.plotly_chart(px.line(path, x="event_ts", y="ground_speed_knots", title="Ground speed over time", labels={"event_ts": "UTC time", "ground_speed_knots": "Ground speed (knots)"}), width="stretch")
        st.caption("ADS-B observations are an independent sample and are not matched to BTS flight records.")

st.divider()
st.markdown("Built with **PySpark | Kafka | PostgreSQL | dbt | Streamlit** &nbsp; | &nbsp; [GitHub repository](https://github.com/ibai71/flightpulse)")

