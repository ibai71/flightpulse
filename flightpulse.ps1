param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "bts", "adsb", "test", "quality", "down", "help")]
    [string]$Action = "help",
    [string]$StartMonth = "2026-05",
    [string]$EndMonth = "2026-07",
    [string]$Airport = "KJFK",
    [string]$Date = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param([string[]]$Arguments)

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed (exit code $LASTEXITCODE); review the command output above."
    }
}

function Build-Runner {
    Invoke-Compose -Arguments @("build", "flightpulse")
}

function Start-Services {
    Invoke-Compose -Arguments @("up", "-d", "--wait", "postgres", "kafka")
}

function Invoke-Runner {
    param([string[]]$Command)

    Invoke-Compose -Arguments (@("run", "--rm", "--no-deps", "flightpulse") + $Command)
}

switch ($Action) {
    "setup" {
        Build-Runner
        Start-Services
        Write-Host "FlightPulse is ready. Run .\flightpulse.ps1 bts to build BTS data."
    }
    "bts" {
        Build-Runner
        Start-Services
        Invoke-Runner -Command @("ingest-bts", "--start-month", $StartMonth, "--end-month", $EndMonth)
        Invoke-Runner -Command @("build-bts", "--start-month", $StartMonth, "--end-month", $EndMonth)
        Invoke-Runner -Command @("dbt-run")
    }
    "adsb" {
        if (-not $Date) {
            throw "Pass an available archive date, e.g. .\flightpulse.ps1 adsb -Airport KJFK -Date 2026-04-30"
        }
        Build-Runner
        Start-Services
        Invoke-Runner -Command @("fetch-adsb", "--airport", $Airport, "--date", $Date)
        Invoke-Runner -Command @("produce-adsb")
        Invoke-Runner -Command @("stream-adsb")
        Invoke-Runner -Command @("load-adsb")
        Invoke-Runner -Command @("dbt-run")
    }
    "test" {
        Build-Runner
        Invoke-Compose -Arguments @("run", "--rm", "--no-deps", "--entrypoint", "python", "flightpulse", "-m", "pytest")
    }
    "quality" {
        Build-Runner
        Start-Services
        Invoke-Compose -Arguments @("run", "--rm", "--no-deps", "--entrypoint", "python", "flightpulse", "-m", "pytest")
        Invoke-Runner -Command @("dbt-test")
    }
    "down" {
        Invoke-Compose -Arguments @("down")
    }
    "help" {
        @"
FlightPulse for Windows (Docker Desktop required)

  .\flightpulse.ps1 setup             Build app image and start PostgreSQL + Kafka
  .\flightpulse.ps1 bts               Run the default May-July 2026 BTS pipeline
  .\flightpulse.ps1 bts -StartMonth 2025-01 -EndMonth 2025-03
  .\flightpulse.ps1 adsb -Airport KJFK -Date YYYY-MM-DD
  .\flightpulse.ps1 test              Run fixture-based tests in Linux
  .\flightpulse.ps1 quality           Run pytest and dbt tests
  .\flightpulse.ps1 down              Stop services
"@
    }
}
