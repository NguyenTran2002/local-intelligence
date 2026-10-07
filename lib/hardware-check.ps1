# Read-only hardware survey for onboarding. Prints one JSON object; changes nothing.
#   powershell -NoProfile -ExecutionPolicy Bypass -File lib\hardware-check.ps1
# Feed the output to lib\plan-config.py.
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot

$out = [ordered]@{
    os      = (Get-CimInstance Win32_OperatingSystem).Caption
    os_build = [Environment]::OSVersion.Version.ToString()
    cpu     = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
    ram_mib = [int]((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB)
    nvidia_smi = $false
    nvidia_gpus = @()
    other_display_adapters = @()
    llama_server_running = [bool](Get-Process llama-server -ErrorAction SilentlyContinue)
    repo_drive_free_gb = $null
    python = $null
    numpy = $null
    claude_version = $null
}

# --- NVIDIA GPUs (nvidia-smi ships with the driver) ---
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    $out.nvidia_smi = $true
    $fields = 'index,name,memory.total,memory.used,driver_version,compute_cap,display_active,display_mode'
    $rows = & nvidia-smi "--query-gpu=$fields" --format=csv,noheader,nounits 2>$null
    foreach ($r in $rows) {
        $c = $r -split ',\s*'
        if ($c.Count -lt 8) { continue }
        $out.nvidia_gpus += [ordered]@{
            index          = [int]$c[0]
            name           = $c[1].Trim()
            vram_total_mib = [int]$c[2]
            vram_used_mib  = [int]$c[3]
            driver         = $c[4].Trim()
            compute_cap    = $c[5].Trim()
            display_active = $c[6].Trim()   # Enabled = a monitor/desktop is drawing on this GPU right now
            display_mode   = $c[7].Trim()
        }
    }
}

# --- every display adapter Windows knows (an iGPU shows up here) ---
foreach ($v in Get-CimInstance Win32_VideoController) {
    if ($v.Name -notmatch 'NVIDIA') {
        $out.other_display_adapters += [ordered]@{
            name = $v.Name
            status = $v.Status
            driving_a_display = [bool]$v.CurrentHorizontalResolution
        }
    }
}

# --- free space on the drive holding this repo (models need 12-75 GB) ---
$drive = (Get-Item $root).PSDrive
if ($drive) { $out.repo_drive_free_gb = [math]::Round($drive.Free / 1GB, 1) }

# --- Python (the ZDR log filter and these helpers need it) ---
$py = & py -3 -c "import sys;print(sys.version.split()[0])" 2>$null
if ($LASTEXITCODE -eq 0 -and $py) {
    $out.python = "$py".Trim()
    $np = & py -3 -c "import numpy;print(numpy.__version__)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $np) { $out.numpy = "$np".Trim() }
}

# --- Claude Code ---
$cv = & claude --version 2>$null
if ($cv) { $out.claude_version = ("$cv" -split '\s+')[0] }

$out | ConvertTo-Json -Depth 4
