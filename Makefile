.DEFAULT_GOAL := help
SHELL := /bin/bash

START_MONTH ?= 2026-05
END_MONTH ?= 2026-07
AIRPORT ?= KJFK
ADS_B_DATE ?=

.PHONY: help up down bts-ingest bts-build bts-pipeline adsb-fetch adsb-produce adsb-stream adsb-load adsb-demo dbt-run quality test

help:
	@echo "FlightPulse commands:"
	@echo "  make up                                  Start PostgreSQL and Kafka"
	@echo "  make bts-ingest START_MONTH=YYYY-MM END_MONTH=YYYY-MM"
	@echo "  make bts-build                           Transform BTS and load PostgreSQL staging"
	@echo "  make bts-pipeline                        Ingest and build BTS"
	@echo "  make adsb-fetch AIRPORT=KJFK ADS_B_DATE=YYYY-MM-DD"
	@echo "  make adsb-demo                           Produce, stream, load, and model ADS-B"
	@echo "  make quality                             Run pytest and dbt tests"
	@echo "  make down                                Stop local services"

up:
	docker compose up -d --wait postgres kafka

down:
	docker compose down

bts-ingest:
	python -m flightpulse.cli ingest-bts --start-month $(START_MONTH) --end-month $(END_MONTH)

bts-build:
	python -m flightpulse.cli build-bts --start-month $(START_MONTH) --end-month $(END_MONTH)

bts-pipeline: up bts-ingest bts-build dbt-run

adsb-fetch:
	python -m flightpulse.cli fetch-adsb --airport $(AIRPORT) $(if $(ADS_B_DATE),--date $(ADS_B_DATE),)

adsb-produce:
	python -m flightpulse.cli produce-adsb

adsb-stream:
	python -m flightpulse.cli stream-adsb

adsb-load:
	python -m flightpulse.cli load-adsb

adsb-demo: up adsb-fetch adsb-produce adsb-stream adsb-load dbt-run

dbt-run:
	python -m flightpulse.cli dbt-run

quality: dbt-run
	pytest
	python -m flightpulse.cli dbt-test

test:
	pytest
