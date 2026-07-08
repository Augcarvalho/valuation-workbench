# Refresh-and-scrape for the evbridge_formula sheet (companion to
# export_capiq_ev_bridge.ps1, which builds the sheet).
#
# Attaches to running Excel (or starts it normally so the Cap IQ XLL loads),
# opens the watchlist workbook if needed, fires the Cap IQ "Refresh Data >
# All Sheets" ribbon action, then patiently polls the sheet until every CIQ
# cell resolves. EVERY COM call is retried: while the add-in refreshes, Excel
# rejects external calls (RPC_E_CALL_REJECTED) - that is normal, not fatal.
# Values are saved and written to ev_bridge_patch.csv.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
$WorkbookPath = Join-Path $OutDir "capiq_watchlist_workbook.xlsx"
$PatchPath = Join-Path $OutDir "ev_bridge_patch.csv"

function Invoke-ComRetry([scriptblock]$Block, [int]$Tries = 40, [int]$SleepSec = 8) {
    for ($i = 1; $i -le $Tries; $i++) {
        try { return & $Block }
        catch {
            if ($i -eq $Tries) { throw }
            Write-Host "COM busy (try $i/$Tries): $($_.Exception.Message.Split("`n")[0])"
            Start-Sleep -Seconds $SleepSec
        }
    }
}

# --- Attach / start Excel ------------------------------------------------------
$Excel = $null
try { $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application") } catch {}
if ($null -eq $Excel) {
    Write-Host "Starting Excel normally (XLL add-ins load)..."
    Start-Process "excel.exe"
    $Deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 5
        try { $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application") } catch {}
    } while ($null -eq $Excel -and (Get-Date) -lt $Deadline)
    if ($null -eq $Excel) { throw "Could not attach to Excel." }
    Start-Sleep -Seconds 20
}
Invoke-ComRetry { $Excel.Visible = $true; $Excel.DisplayAlerts = $false } | Out-Null

# --- Open workbook if needed ----------------------------------------------------
$Workbook = Invoke-ComRetry {
    $wb = $null
    foreach ($W in $Excel.Workbooks) { if ($W.Name -like "capiq_watchlist_workbook*") { $wb = $W } }
    if ($null -eq $wb) { $wb = $Excel.Workbooks.Open($WorkbookPath) }
    $wb
}
Start-Sleep -Seconds 10   # add-in settles after workbook open
$Sheet = Invoke-ComRetry {
    $s = $null
    foreach ($S in $Workbook.Worksheets) { if ($S.Name -eq "evbridge_formula") { $s = $S } }
    if ($null -eq $s) { throw "evbridge_formula sheet not found - run export_capiq_ev_bridge.ps1 first." }
    $s
}

# --- Fire Cap IQ refresh (All Sheets) --------------------------------------------
$Process = Get-Process EXCEL | Select-Object -First 1
$Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
$NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
$Tab = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "S&P Cap IQ Pro")))
if ($null -eq $Tab) { throw "S&P Cap IQ Pro ribbon not found - add-in not loaded." }
try { $Tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() | Out-Null } catch {}
Start-Sleep -Milliseconds 800
$Refresh = $null
foreach ($El in $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
    $ct = $El.Current.ControlType.ProgrammaticName
    if ($El.Current.Name -eq "Refresh Data" -and ($ct -eq "ControlType.SplitButton" -or $ct -eq "ControlType.Button" -or $ct -eq "ControlType.MenuItem")) {
        $Refresh = $El
        if ($ct -eq "ControlType.SplitButton") { break }
    }
}
if ($null -eq $Refresh) { throw "Refresh Data control not found." }
$expanded = $false
try { $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null; $expanded = $true } catch {}
if (-not $expanded) { try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {} }
Start-Sleep -Milliseconds 800
$AllSheets = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")))
if ($null -eq $AllSheets) { throw "'All Sheets' option not found." }
$AllSheets.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null
Write-Host "Refresh fired; polling until the evbridge sheet resolves..."
Start-Sleep -Seconds 20   # let #PEND propagate before the first check

# --- Poll until resolved -----------------------------------------------------------
$Deadline = (Get-Date).AddSeconds(1500)
$State = $null
do {
    $State = Invoke-ComRetry {
        $pending = 0; $empty = 0; $nameErr = 0; $numeric = 0
        for ($r = 2; $r -le 67; $r++) {
            for ($c = 2; $c -le 8; $c++) {
                $t = ([string]$Sheet.Cells.Item($r, $c).Text).Trim()
                if ($t -eq "#PEND") { $pending++ }
                elseif ($t -eq "#NAME?") { $nameErr++ }
                elseif ($t -eq "") { $empty++ }
                else { $numeric++ }
            }
        }
        @{pending = $pending; empty = $empty; name_err = $nameErr; values = $numeric}
    }
    Write-Host "settle: values=$($State.values) pending=$($State.pending) empty=$($State.empty) name_err=$($State.name_err)"
    if ($State.pending -eq 0 -and $State.values -gt 100) { break }
    Start-Sleep -Seconds 15
} while ((Get-Date) -lt $Deadline)
if ($State.name_err -gt 100) { throw "CIQ returned #NAME? - sign in to S&P Capital IQ Pro." }
if ($State.pending -gt 0) { throw "Timed out with $($State.pending) cells still #PEND." }
if ($State.values -le 100) { throw "Sheet never produced values." }

Invoke-ComRetry { $Workbook.Save() | Out-Null } 20 8
Write-Host "Workbook saved with resolved values."

# --- Scrape ---------------------------------------------------------------------------
function To-Double($Value) {
    if ($null -eq $Value) { return $null }
    $Text = ([string]$Value).Trim()
    if ($Text -eq "" -or $Text -like "#*" -or $Text -like "(*Invalid*" -or $Text -like "CIQ*") { return $null }
    $n = 0.0
    if ([double]::TryParse($Text, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::InvariantCulture, [ref]$n)) { return $n }
    if ([double]::TryParse($Text, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::CurrentCulture, [ref]$n)) { return $n }
    return $null
}
function SerialToDate($Value) {
    $s = To-Double $Value
    if ($null -eq $s) { return $null }
    return ([datetime]"1899-12-30").AddDays([int][Math]::Round($s)).ToString("yyyy-MM-dd")
}

$Rows = Invoke-ComRetry {
    $acc = @()
    for ($r = 2; $r -le 67; $r++) {
        $Id = [string]$Sheet.Cells.Item($r, 1).Text
        if (-not $Id) { continue }
        $acc += [PSCustomObject]@{
            company_id = $Id
            period = SerialToDate ([string]$Sheet.Cells.Item($r, 2).Text)
            minority_interest = To-Double ([string]$Sheet.Cells.Item($r, 3).Text)
            preferred_equity = To-Double ([string]$Sheet.Cells.Item($r, 4).Text)
            lease_liabilities = To-Double ([string]$Sheet.Cells.Item($r, 5).Text)
            pension_liabilities = To-Double ([string]$Sheet.Cells.Item($r, 6).Text)
            cash_st_invest = To-Double ([string]$Sheet.Cells.Item($r, 7).Text)
            tangible_common_equity = To-Double ([string]$Sheet.Cells.Item($r, 8).Text)
        }
    }
    $acc
}
$Rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $PatchPath
$WithCash = @($Rows | Where-Object { $null -ne $_.cash_st_invest }).Count
$WithMin = @($Rows | Where-Object { $null -ne $_.minority_interest }).Count
Write-Host "Wrote $($Rows.Count) rows -> $PatchPath (cash_st_invest=$WithCash, minority=$WithMin)"
