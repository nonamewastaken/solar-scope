# Sets up the project on Windows.
# Run it from the project folder in PowerShell with:  .\setup.ps1
$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python is not installed. See docs/environment-setup.md, then run this again."
  exit 1
}

Write-Host "Creating the virtual environment in .venv"
python -m venv .venv

Write-Host "Installing dependencies"
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

Write-Host ""
Write-Host "Done. Activate the environment with:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Then check everything works with:"
Write-Host "    python src\app.py"
Write-Host "    pytest"
