[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBase,

    [Parameter(Mandatory = $true)]
    [ValidateSet("Status", "RebuildWatchlist", "Preflight", "Arm", "RunEntryOnce", "Reconcile", "Disarm")]
    [string]$Action,

    [int]$Count = 50,
    [double]$PriceCapKrw = 1000000,
    [string]$Confirmation
)

$ErrorActionPreference = "Stop"
$ApiBase = $ApiBase.TrimEnd('/')

function Invoke-OperationTest4Json {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $params = @{
        Method = $Method
        Uri = "$ApiBase$Path"
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20)
    }
    Invoke-RestMethod @params
}

function Get-ExactConfirmation {
    param([string]$Expected)
    if (-not [string]::IsNullOrWhiteSpace($Confirmation)) {
        return $Confirmation.Trim()
    }
    Read-Host "Type exact confirmation: $Expected"
}

function Write-Json {
    param([object]$Value)
    $Value | ConvertTo-Json -Depth 30
}

switch ($Action) {
    "Status" {
        Write-Json (Invoke-OperationTest4Json -Method Get -Path "/app/operation-test4/status")
        break
    }

    "RebuildWatchlist" {
        Write-Json (Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/watchlist/rebuild" -Body @{
                count = $Count
                price_cap_krw = $PriceCapKrw
            })
        break
    }

    "Preflight" {
        Write-Json (Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/entry/preflight-once")
        break
    }

    "Arm" {
        $expected = "ENABLE TEST4 FULL CYCLE"
        $provided = Get-ExactConfirmation -Expected $expected
        if ($provided -ne $expected) {
            Write-Json @{ status = "blocked"; reason = "operator_confirmation_required" }
            break
        }

        $enabled = Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/enable-live" -Body @{
            confirm_live = $true
            confirmation = $provided
        }
        $null = Invoke-OperationTest4Json -Method Put -Path "/ops/settings" -Body @{
            dry_run = $false
            kill_switch = $false
        }
        $readiness = Invoke-OperationTest4Json -Method Get -Path "/app/operation-test4/readiness"
        if ($readiness.status -ne "ready") {
            $disarm = Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/disable"
            Write-Json @{ status = "blocked"; reason = "readiness_not_ready"; enable = $enabled; readiness = $readiness; disarm = $disarm }
            break
        }
        Write-Json @{ status = "ready"; enable = $enabled; readiness = $readiness }
        break
    }

    "RunEntryOnce" {
        $preflight = Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/entry/preflight-once"
        Write-Output "candidate=$($preflight.candidate.symbol)"
        Write-Output "current_price=$($preflight.candidate.current_price)"
        Write-Output "equity=$($preflight.account.equity)"
        Write-Output "orderable_cash=$($preflight.account.orderable_cash)"
        Write-Output "quantity=$($preflight.candidate.quantity)"
        Write-Output "estimated_notional=$($preflight.candidate.estimated_notional)"
        Write-Output "effective_position_pct=$($preflight.candidate.effective_position_pct)"
        Write-Output "score=$($preflight.candidate.final_buy_score)"
        Write-Output ("risk_flags=" + (($preflight.candidate.risk_flags | ConvertTo-Json -Compress -Depth 10)))

        $expected = "RUN TEST4 LIVE ENTRY ONCE"
        $provided = Get-ExactConfirmation -Expected $expected
        if ($provided -ne $expected) {
            Write-Json @{ status = "blocked"; reason = "operator_confirmation_required"; preflight = $preflight }
            break
        }
        Write-Json (Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/entry/run-once" -Body @{
                confirm_live = $true
                confirmation = $provided
            })
        break
    }

    "Reconcile" {
        Write-Json (Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/reconcile-once")
        break
    }

    "Disarm" {
        $disabled = Invoke-OperationTest4Json -Method Post -Path "/app/operation-test4/disable"
        $null = Invoke-OperationTest4Json -Method Put -Path "/ops/settings" -Body @{
            dry_run = $true
            kill_switch = $true
        }
        Write-Json $disabled
        break
    }
}