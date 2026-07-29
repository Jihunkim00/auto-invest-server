param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$Python = "",
  [Nullable[Double]]$MaxNotionalKrw = $null,
  [Nullable[Double]]$MaxNotionalPct = $null,
  [string]$Slot = "manual",
  [string]$LogDir = ""
)

$ErrorActionPreference = "Stop"

if ($null -eq $MaxNotionalKrw) {
  if ($env:STAGE3_MAX_NOTIONAL_KRW) {
    $MaxNotionalKrw = [Double]$env:STAGE3_MAX_NOTIONAL_KRW
  }
  else {
    $MaxNotionalKrw = 55000.0
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

if ($MaxNotionalKrw -le 0) {
  throw "MaxNotionalKrw must be positive."
}

if ($MaxNotionalPct -le 0 -or $MaxNotionalPct -gt 1) {
  throw "MaxNotionalPct must be > 0 and <= 1."
}

if (-not $LogDir) {
  $LogDir = Join-Path $Root "stage3_logs"
}

$trendBuilder = Join-Path $Root "scripts\stage3_build_trend_watchlist.py"
$sourceUniverse = Join-Path $Root "config\watchlist_kr.stage3.universe100.yaml"
$targetWatchlist = Join-Path $Root "config\watchlist_kr.yaml"

if (-not $Python) {
  $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) {
    $Python = $venvPython
  }
  else {
    $Python = "python"
  }
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeSlot = ($Slot -replace "[^0-9A-Za-z_.-]", "_")
$logPath = Join-Path $LogDir "scheduled_check_${timestamp}_${safeSlot}.log"
$previewPath = Join-Path $LogDir "scheduled_preview_${timestamp}_${safeSlot}.json"
$preflightPath = Join-Path $LogDir "scheduled_preflight_${timestamp}_${safeSlot}.json"
$reportPath = Join-Path $LogDir "trend_watchlist_report_${timestamp}_${safeSlot}.json"
$lockPath = Join-Path $LogDir "stage3_scheduled_check_${safeSlot}.lock"
$lockStream = $null

function Write-Log {
  param([string]$Message)

  $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
  Write-Host $line
  Add-Content -Path $logPath -Value $line -Encoding UTF8
}

function Invoke-ApiJson {
  param(
    [string]$Method,
    [string]$Path,
    [object]$Body = $null
  )

  $uri = "$BaseUrl$Path"
  if ($null -eq $Body) {
    return Invoke-RestMethod `
      -Method $Method `
      -Uri $uri `
      -ContentType "application/json"
  }

  return Invoke-RestMethod `
    -Method $Method `
    -Uri $uri `
    -ContentType "application/json" `
    -Body ($Body | ConvertTo-Json -Depth 30)
}

function Get-Number {
  param(
    [object]$Item,
    [string[]]$Names
  )

  foreach ($name in $Names) {
    if ($null -ne $Item.$name) {
      try {
        return [Double]$Item.$name
      }
      catch {
      }
    }
  }
  return $null
}

function Get-CandidateItems {
  param([object]$Preview)

  foreach ($name in @(
    "items",
    "final_ranked_candidates",
    "ranked_candidates",
    "candidates",
    "watchlist"
  )) {
    if ($null -ne $Preview.$name) {
      return @($Preview.$name)
    }
  }
  return @()
}

function Write-JsonFile {
  param(
    [object]$Payload,
    [string]$Path
  )

  $Payload |
    ConvertTo-Json -Depth 60 |
    Set-Content -Path $Path -Encoding UTF8
}

function Read-TechnicalReport {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    Write-Log "technical_report_parse_failed=true"
    Write-Log "technical report error=file_not_found"
    Write-Log "preflight_executed=false"
    Write-Log "HOLD: technical report unavailable"
    return $null
  }

  $content = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
  if ([string]::IsNullOrWhiteSpace($content)) {
    Write-Log "technical_report_parse_failed=true"
    Write-Log "technical report error=empty_file"
    Write-Log "preflight_executed=false"
    Write-Log "HOLD: technical report unavailable"
    return $null
  }

  try {
    return $content | ConvertFrom-Json -ErrorAction Stop
  }
  catch {
    $message = $_.Exception.Message
    if ($message.Length -gt 180) {
      $message = $message.Substring(0, 180) + "..."
    }
    Write-Log "technical_report_parse_failed=true"
    Write-Log "technical report error=json_parse_failed: $message"
    Write-Log "preflight_executed=false"
    Write-Log "HOLD: technical report unavailable"
    return $null
  }
}

$SafeSettings = @{
  dry_run = $true
  kill_switch = $true
  scheduler_enabled = $false

  bot_enabled = $false
  portfolio_orchestrator_enabled = $false
  portfolio_orchestrator_allow_live_orders = $false

  kis_scheduler_enabled = $false
  kis_scheduler_dry_run = $true
  kis_scheduler_live_enabled = $false
  kis_scheduler_allow_real_orders = $false
  kis_scheduler_configured_allow_real_orders = $false
  kis_scheduler_buy_enabled = $false
  kis_scheduler_sell_enabled = $false
  kis_scheduler_allow_limited_auto_buy = $false
  kis_scheduler_allow_limited_auto_sell = $false

  kis_live_auto_buy_enabled = $false
  kis_limited_auto_buy_enabled = $false
  kis_live_auto_sell_enabled = $false
  kis_limited_auto_sell_enabled = $false
  kis_limited_auto_buy_max_notional_pct = 0.80
  kis_limited_auto_buy_max_notional_krw = 50000.0
}

$PreflightSettings = $SafeSettings.Clone()
$PreflightSettings["dry_run"] = $true
$PreflightSettings["kill_switch"] = $false
$PreflightSettings["kis_live_auto_buy_enabled"] = $true
$PreflightSettings["kis_limited_auto_buy_enabled"] = $true
$PreflightSettings["kis_limited_auto_buy_readiness_enabled"] = $true
$PreflightSettings["kis_limited_auto_buy_shadow_enabled"] = $true
$PreflightSettings["kis_limited_auto_buy_requires_shadow_review"] = $true
$PreflightSettings["kis_limited_auto_buy_min_final_score"] = 75.0
$PreflightSettings["kis_limited_auto_buy_min_confidence"] = 0.70
$PreflightSettings["kis_limited_auto_buy_max_orders_per_day"] = 1
$PreflightSettings["kis_limited_auto_buy_max_positions"] = 1
$PreflightSettings["kis_limited_auto_buy_max_notional_pct"] = [Double]$MaxNotionalPct
$PreflightSettings["kis_limited_auto_buy_max_notional_krw"] = [Double]$MaxNotionalKrw
$PreflightSettings["kis_limited_auto_buy_min_cash_buffer_krw"] = 0
$PreflightSettings["kis_limited_auto_buy_block_if_position_exists"] = $true
$PreflightSettings["kis_limited_auto_buy_block_if_open_order_exists"] = $true
$PreflightSettings["kis_limited_auto_buy_allow_reentry_same_day"] = $false
$PreflightSettings["kis_limited_auto_buy_require_market_open"] = $true
$PreflightSettings["kis_limited_auto_buy_no_new_entry_after"] = "14:50"
$PreflightSettings["kis_limited_auto_buy_allow_gpt_hard_block"] = $false
$PreflightSettings["kis_limited_auto_buy_requires_existing_sell_guards"] = $true
$PreflightSettings["kis_live_auto_sell_enabled"] = $true
$PreflightSettings["kis_limited_auto_sell_enabled"] = $true
$PreflightSettings["kis_limited_auto_stop_loss_enabled"] = $true
$PreflightSettings["kis_limited_auto_sell_stop_loss_enabled"] = $true
$PreflightSettings["kis_limited_auto_sell_max_orders_per_day"] = 1
$PreflightSettings["kis_limited_auto_take_profit_enabled"] = $false
$PreflightSettings["kis_limited_auto_sell_take_profit_enabled"] = $false
$PreflightSettings["take_profit_enabled"] = $false

function Invoke-Stage3Check {
  $exitCode = 0
  try {
    try {
      $lockStream = [System.IO.File]::Open(
        $lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
      )
    }
    catch {
      Write-Log "SKIP: slot lock is already held. slot=$Slot"
      return 0
    }

    Write-Log "Scheduled KIS check started. slot=$Slot"
    Write-Log "max_notional_krw=$([Double]$MaxNotionalKrw)"
    Write-Log "max_notional_pct=$([Double]$MaxNotionalPct)"
    Write-Log "real_order_submitted=false"
    Write-Log "broker_submit_called=false"

    if (-not (Test-Path $trendBuilder)) {
      throw "Trend builder not found: $trendBuilder"
    }

    if (-not (Test-Path $sourceUniverse)) {
      throw "Stage 3 source universe not found: $sourceUniverse"
    }

    Invoke-ApiJson -Method Put -Path "/ops/settings" -Body $SafeSettings |
      Out-Null
    Write-Log "Safe settings applied."

    $checkArgs = @(
      $trendBuilder,
      "--source-watchlist",
      $sourceUniverse,
      "--require-source-count",
      "100",
      "--check-source-only"
    )
    $sourceCheckOutput = & $Python @checkArgs 2>&1
    $sourceCheckExitCode = $LASTEXITCODE
    $sourceCheckOutput | ForEach-Object { Write-Log $_ }
    if ($sourceCheckExitCode -ne 0) {
      throw "Source universe check failed: exit=$sourceCheckExitCode"
    }

    $sourceSummaryText = ($sourceCheckOutput -join "`n")
    $sourceSummary = $sourceSummaryText | ConvertFrom-Json
    Write-Log "source symbol count=$($sourceSummary.source_symbol_count)"
    if ([Int32]$sourceSummary.source_symbol_count -ne 100) {
      throw "Source universe count is not 100."
    }

    Write-Log "Refreshing technical watchlist."
    $builderArgs = @(
      $trendBuilder,
      "--source-watchlist",
      $sourceUniverse,
      "--target-watchlist",
      $targetWatchlist,
      "--report-dir",
      $LogDir,
      "--max-notional-krw",
      ([string][Double]$MaxNotionalKrw),
      "--max-notional-pct",
      ([string][Double]$MaxNotionalPct),
      "--report-path",
      $reportPath,
      "--require-source-count",
      "100"
    )
    $builderOutput = & $Python @builderArgs 2>&1
    $builderExitCode = $LASTEXITCODE
    $builderOutput | ForEach-Object { Write-Log $_ }
    Write-Log "Trend builder exit code=$builderExitCode"

    if ($builderExitCode -eq 2) {
      Write-Log "technical pass count=0"
      Write-Log "top candidate=none"
      Write-Log "preflight_executed=false"
      Write-Log "HOLD: no symbol passed technical filters."
      return 0
    }

    if ($builderExitCode -ne 0) {
      throw "Trend builder failed: exit=$builderExitCode"
    }

    $trendReport = Read-TechnicalReport -Path $reportPath
    if ($null -eq $trendReport) {
      return 0
    }
    Write-Log "technical_report_parse_failed=false"
    Write-Log "technical report path=$reportPath"
    Write-Log "technical pass count=$($trendReport.technical_pass_count)"
    if ($null -ne $trendReport.top_candidate) {
      Write-Log "top candidate=$($trendReport.top_candidate.symbol)"
    }
    else {
      Write-Log "top candidate=none"
    }

    Invoke-ApiJson -Method Put -Path "/ops/settings" -Body $PreflightSettings |
      Out-Null
    Write-Log "Preview settings applied."

    Start-Sleep -Seconds 3

    $preview = Invoke-ApiJson `
      -Method Post `
      -Path "/kis/watchlist/preview?gate_level=2"
    Write-JsonFile -Payload $preview -Path $previewPath

    $items = @(Get-CandidateItems -Preview $preview)
    if ($items.Count -eq 0) {
      Write-Log "preflight_executed=false"
      Write-Log "HOLD: preview returned no candidates."
      return 0
    }

    $ranked = @(
      $items |
        Sort-Object -Descending -Property @{
          Expression = {
            $value = Get-Number $_ @("final_buy_score", "final_score", "score")
            if ($null -eq $value) { -1.0 } else { $value }
          }
        }
    )
    $top = $ranked | Select-Object -First 1
    $topQuant = Get-Number $top @("quant_buy_score", "quant_score")
    $topFinal = Get-Number $top @("final_buy_score", "final_score", "score")
    $topConfidence = Get-Number $top @("confidence", "gpt_confidence")
    Write-Log (
      "Preview top symbol=$($top.symbol), " +
      "quant=$topQuant, " +
      "final=$topFinal, " +
      "confidence=$topConfidence"
    )
    Write-Log "quant score=$topQuant"
    Write-Log "final score=$topFinal"
    Write-Log "confidence=$topConfidence"

    $scoreCandidates = @(
      $items |
        Where-Object {
          $quant = Get-Number $_ @("quant_buy_score", "quant_score")
          $final = Get-Number $_ @("final_buy_score", "final_score", "score")
          $confidence = Get-Number $_ @("confidence", "gpt_confidence")
          $indicatorOk = $_.indicator_status -eq "ok"
          $indicatorOk -and
            $null -ne $quant -and $quant -ge 75 -and
            $null -ne $final -and $final -ge 75 -and
            $null -ne $confidence -and $confidence -ge 0.70
        } |
        Sort-Object -Descending -Property @{
          Expression = {
            Get-Number $_ @("final_buy_score", "final_score", "score")
          }
        }
    )

    if ($scoreCandidates.Count -eq 0) {
      Write-Log (
        "HOLD: no candidate passed " +
        "quant>=75, final>=75, confidence>=0.70."
      )
      Write-Log "preflight_executed=false"
      return 0
    }

    $scoreTop = $scoreCandidates | Select-Object -First 1
    $scoreTopFinal = Get-Number $scoreTop @("final_buy_score", "final_score", "score")
    Write-Log (
      "Score candidate found: " +
      "$($scoreTop.symbol), final=$scoreTopFinal"
    )

    Start-Sleep -Seconds 10
    $buyPreflight = Invoke-ApiJson `
      -Method Post `
      -Path "/kis/limited-auto-buy/preflight-once?gate_level=2"
    Write-JsonFile -Payload $buyPreflight -Path $preflightPath
    Write-Log "preflight_executed=true"

    $realOrderSubmitted = $buyPreflight.real_order_submitted -eq $true
    $brokerSubmitCalled = $buyPreflight.broker_submit_called -eq $true
    Write-Log (
      "Preflight result=$($buyPreflight.result), " +
      "action=$($buyPreflight.action), " +
      "reason=$($buyPreflight.reason)"
    )
    Write-Log "real_order_submitted=$($realOrderSubmitted.ToString().ToLowerInvariant())"
    Write-Log "broker_submit_called=$($brokerSubmitCalled.ToString().ToLowerInvariant())"

    if ($realOrderSubmitted -or $brokerSubmitCalled) {
      throw "Preflight unexpectedly reported an order submission path."
    }

    Write-Log "READY FOR MANUAL REVIEW ONLY. No order submitted."
    return $exitCode
  }
  catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    $_ | Out-String | Add-Content -Path $logPath -Encoding UTF8
    return 1
  }
  finally {
    try {
      Invoke-ApiJson -Method Put -Path "/ops/settings" -Body $SafeSettings |
        Out-Null
      Write-Log "safe settings restored"
    }
    catch {
      Write-Host "WARNING: safe settings restore failed."
      Write-Host $_.Exception.Message
    }

    if ($null -ne $lockStream) {
      $lockStream.Dispose()
    }
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
  }
}

$resultCode = Invoke-Stage3Check
exit $resultCode
