param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [DateTime]$RunDate = (Get-Date).Date,
  [string[]]$Times = @("12:00", "14:30"),
  [Nullable[Double]]$MaxNotionalKrw = $null,
  [Nullable[Double]]$MaxNotionalPct = $null,
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"

if ($null -eq $MaxNotionalKrw) {
  if ($env:STAGE3_MAX_NOTIONAL_KRW) {
    $MaxNotionalKrw = [Double]$env:STAGE3_MAX_NOTIONAL_KRW
  }
  else {
    $MaxNotionalKrw = 50000.0
  }
}

if ($null -eq $MaxNotionalPct) {
  if ($env:STAGE3_MAX_NOTIONAL_PCT) {
    $MaxNotionalPct = [Double]$env:STAGE3_MAX_NOTIONAL_PCT
  }
  else {
    $MaxNotionalPct = 0.80
  }
}

function Get-KoreaTimeZone {
  try {
    return [System.TimeZoneInfo]::FindSystemTimeZoneById("Asia/Seoul")
  }
  catch {
    return [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
  }
}

function Get-PowerShellExe {
  $windowsPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
  if ($null -ne $windowsPowerShell) {
    return $windowsPowerShell.Source
  }

  $powerShellCore = Get-Command pwsh -ErrorAction SilentlyContinue
  if ($null -ne $powerShellCore) {
    return $powerShellCore.Source
  }

  throw "PowerShell executable was not found."
}

function Normalize-ScheduleTimes {
  param(
    [string[]]$RawTimes
  )

  $normalizedTimes = @()
  $trimChars = [char[]]@(
    [char]0x20,
    [char]0x09,
    [char]0x0D,
    [char]0x0A,
    [char]0x27,
    [char]0x22
  )

  foreach ($rawTime in $RawTimes) {
    foreach ($timePart in ([string]$rawTime).Split(",")) {
      $timeText = $timePart.Trim($trimChars)
      $parsedTime = [DateTime]::MinValue

      if (-not [DateTime]::TryParseExact(
          $timeText,
          "HH:mm",
          [System.Globalization.CultureInfo]::InvariantCulture,
          [System.Globalization.DateTimeStyles]::None,
          [ref]$parsedTime
        )) {
        throw "Invalid schedule time: '$timeText'. Expected HH:mm."
      }

      $normalizedTimes += $timeText
    }
  }

  return $normalizedTimes
}

$checkScript = Join-Path $Root "scripts\stage3_scheduled_check.ps1"
if (-not (Test-Path $checkScript)) {
  throw "Check script not found: $checkScript"
}

$koreaTz = Get-KoreaTimeZone
$powerShellExe = Get-PowerShellExe
$runDateText = $RunDate.ToString("yyyy-MM-dd")
$scheduleTimes = Normalize-ScheduleTimes -RawTimes $Times

foreach ($timeText in $scheduleTimes) {
  $targetText = "$runDateText $timeText"
  $targetKst = [DateTime]::ParseExact(
    $targetText,
    "yyyy-MM-dd HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture
  )
  $nowKst = [System.TimeZoneInfo]::ConvertTimeFromUtc(
    [DateTime]::UtcNow,
    $koreaTz
  )

  if ($targetKst -le $nowKst) {
    Write-Host "Skipping past target: $targetText Asia/Seoul"
    continue
  }

  $waitSeconds = [Math]::Ceiling(($targetKst - $nowKst).TotalSeconds)
  Write-Host ""
  Write-Host "Next KIS check: $targetText Asia/Seoul"
  Write-Host "Waiting $waitSeconds seconds."
  Start-Sleep -Seconds $waitSeconds

  $slot = "$($RunDate.ToString('yyyyMMdd'))_$($timeText -replace ':', '')"
  $args = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $checkScript,
    "-Root",
    $Root,
    "-BaseUrl",
    $BaseUrl,
    "-MaxNotionalKrw",
    ([string][Double]$MaxNotionalKrw),
    "-MaxNotionalPct",
    ([string][Double]$MaxNotionalPct),
    "-Slot",
    $slot
  )

  if ($Python) {
    $args += @("-Python", $Python)
  }

  & $powerShellExe @args
  $checkExitCode = $LASTEXITCODE
  if ($checkExitCode -ne 0) {
    Write-Host "Stage 3 check failed for slot=$slot exit=$checkExitCode"
  }
}

Write-Host ""
Write-Host "Scheduled Stage 3 checks completed."
