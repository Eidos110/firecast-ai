<#
.SYNOPSIS
    FireCast Railway Deployment Script (Native Buildpack - No Docker)
    Deploys FireCast to Railway.app using Python buildpacks

.DESCRIPTION
    This script automates deployment without Docker.
    Steps:
    1. Validates prerequisites (Node for React build, Railway CLI)
    2. Builds React frontend locally (npm ci && npm run build)
    3. Verifies build artifacts exist
    4. Deploys both services to Railway via railway up

.NOTES
    Author: Kilo (Senior Software Engineer)
    Date: 2026-05-14
    Requires: Node.js, npm, Railway CLI

.EXAMPLE
    .\deploy.ps1 -Mode Deploy
    Deploys both frontend and API services to Railway.

.EXAMPLE
    .\deploy.ps1 -Mode BuildOnly
    Only builds React frontend without deploying.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Deploy", "BuildOnly", "Status", "Logs", "Frontend", "API")]
    [string]$Mode = "Deploy",

    [Parameter(Mandatory=$false)]
    [string]$ProjectName = "firecast",

    [Parameter(Mandatory=$false)]
    [switch]$SkipReactBuild = $false
)

$ColorInfo = "Cyan"
$ColorSuccess = "Green"
$ColorWarning = "Yellow"
$ColorError = "Red"

function Write-Info($Message) { Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Success($Message) { Write-Host "[OK]   $Message" -ForegroundColor Green }
function Write-Warning($Message) { Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-ErrorMsg($Message) { Write-Host "[ERR]  $Message" -ForegroundColor Red }

function Test-Command($cmd) {
    try { if (Get-Command $cmd -ErrorAction SilentlyContinue) { return $true } } catch {}
    return $false
}

function Invoke-CheckPrerequisites {
    Write-Info "Checking prerequisites..."

    # Node/npm for React build
    if (-not (Test-Command "node")) {
        Write-ErrorMsg "Node.js is not installed. Install from https://nodejs.org"
        exit 1
    }
    $nodeVer = node --version
    Write-Success "Node found: $nodeVer"

    if (-not (Test-Command "npm.cmd")) {
        Write-ErrorMsg "npm is not installed (should come with Node)."
        exit 1
    }
    Write-Success "npm found"

    # Railway CLI
    if (-not (Test-Command "railway")) {
        Write-Warning "Railway CLI not found. Installing..."
        npm install -g @railway/cli
        if (-not (Test-Command "railway")) {
            Write-ErrorMsg "Failed to install Railway CLI. Manual: npm i -g @railway/cli"
            exit 1
        }
    }
    $railwayVer = railway --version
    Write-Success "Railway CLI: $railwayVer"

    # Check Docker not needed
    Write-Info "Native deployment (no Docker) selected.`n"
}

function Invoke-BuildReact {
    param([switch]$Skip = $false)
    if ($Skip) {
        Write-Info "Skipping React build (--SkipReactBuild)"
        return
    }

    Write-Info "Building React frontend (required for Railway native deployment)..."

    $reactDir = "frontend_react"
    if (-not (Test-Path $reactDir)) {
        Write-ErrorMsg "Directory '$reactDir' not found."
        exit 1
    }

    Set-Location $reactDir

    try {
        # Install dependencies (clean install)
        Write-Info "  npm ci (installing dependencies)..."
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }

        # Build
        Write-Info "  npm run build..."
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }

        Write-Success "React build complete: $reactDir/build/"
    }
    catch {
        Write-ErrorMsg "React build failed: $_"
        exit 1
    }
    finally {
        Set-Location ..
    }

    # Verify build output exists
    $buildPath = Join-Path $reactDir "build"
    if (-not (Test-Path $buildPath)) {
        Write-ErrorMsg "Build directory not found: $buildPath"
        exit 1
    }
    Write-Success "Build artifacts verified.`n"
}

function Invoke-Preflight {
    Write-Info "=== FireCast Railway Native Deployment ==="
    Write-Info "Project: FireCast - Fire Risk Prediction System"
    Write-Info "Method: Python buildpacks (no Docker)"
    Write-Info ""

    # Check .env
    if (-not (Test-Path ".env")) {
        Write-Warning ".env file not found. Copy from .env.production and set secrets!"
        Write-Info "  copy .env.production .env"
        Write-Info "  # Then edit: set OPENWEATHER_API_KEY and API_SECRET_KEY"
        $continue = Read-Host "Continue without .env? (y/N)"
        if ($continue -ne "y" -and $continue -ne "Y") { exit 0 }
    }

    # Check git
    if (-not (Test-Path ".git")) {
        Write-Warning "Not a git repository. Railway works without git but version control recommended."
        $continue = Read-Host "Continue? (y/N)"
        if ($continue -ne "y" -and $continue -ne "Y") { exit 0 }
    }

    # Check that railway.toml exists
    if (-not (Test-Path "railway.toml")) {
        Write-ErrorMsg "railway.toml not found in current directory."
        exit 1
    }
}

function Invoke-DeployService($serviceName) {
    Write-Info "Deploying service: $serviceName"
    try {
        # Use --detach to not block; --if-exists updates existing
        $cmd = "railway.cmd up --service $serviceName --detach"
        Write-Info "Running: $cmd"
        Invoke-Expression $cmd
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Deployment of $serviceName initiated."
        } else {
            Write-ErrorMsg "Deployment of $serviceName failed (exit code $LASTEXITCODE)."
            exit 1
        }
    }
    catch {
        Write-ErrorMsg "Error deploying $serviceName: $_"
        exit 1
    }
}

function Invoke-Status {
    try { railway.cmd status } catch { Write-Warning "Could not fetch status." }
}

function Invoke-Logs($service) {
    try {
        if ($service) {
            railway.cmd logs --service $service --tail 100
        } else {
            railway.cmd logs --tail 100
        }
    }
    catch { Write-Warning "Could not fetch logs." }
}

# MAIN
try {
    Invoke-Preflight
    Invoke-CheckPrerequisites
    Invoke-BuildReact -Skip:$SkipReactBuild

    switch ($Mode) {
        "Deploy" {
            # Deploy both services
            Invoke-DeployService "firecast-frontend"
            Start-Sleep -Seconds 5  # brief stagger
            Invoke-DeployService "firecast-api"
            Write-Info "`nDeployment commands sent. Check status:"
            Write-Info "  railway.cmd status"
            Write-Info "Or view dashboard: railway.cmd open"
        }
        "BuildOnly" {
            Write-Success "React build complete. Ready to deploy."
            Write-Info "Run: .\deploy.ps1 -Mode Deploy"
        }
        "Frontend" {
            Invoke-DeployService "firecast-frontend"
        }
        "API" {
            Invoke-DeployService "firecast-api"
        }
        "Status" {
            Invoke-Status
        }
        "Logs" {
            Invoke-Logs $null
        }
    }

    Write-Success "Script finished."
}
catch {
    Write-ErrorMsg "Fatal error: $_"
    exit 1
}
