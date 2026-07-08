# Targeted EV-bridge export: TEV components for the latest fiscal quarter.
#
# Fetches ONLY the balance-sheet items needed to close the EV bridge
# (minority interest, preferred equity, capital leases, pensions, cash incl.
# short-term investments, tangible common equity) for every name in
# companies.csv, without re-running the full 20-quarter watchlist export.
#
# Flow: builds an `evbridge_formula` sheet in the existing watchlist workbook,
# fires the Cap IQ Pro "Refresh Data > All Sheets" ribbon action, polls #PEND,
# scrapes typed values to data_private\capiq_exports\ev_bridge_patch.csv.
# Then run scripts\patch_ev_bridge_fields.py to merge into
# financials_quarterly.csv (latest-period rows) and rebuild the dataset.
#
# Requires Excel with the S&P Capital IQ Pro Add-In signed in. If Excel is not
# running it is started and the workbook opened; if the add-in is not signed
# in, formulas stay #NAME?/#PEND and the script aborts without writing.
#
# Output is licensed data and MUST stay inside data_private/ (gitignored).

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
$WorkbookPath = Join-Path $OutDir "capiq_watchlist_workbook.xlsx"
$CompaniesCsv = Join-Path $OutDir "companies.csv"
if (-not (Test-Path $CompaniesCsv)) { throw "companies.csv not found - run the full export first." }

$Universe = @(Import-Csv $CompaniesCsv | ForEach-Object { $_.company_id })
Write-Host "Universe: $($Universe.Count) companies"

# --- Excel session ---------------------------------------------------------------
# IMPORTANT: Excel created via COM (New-Object) skips XLL add-in loading, so
# CIQ() resolves to #NAME?. Start Excel as a normal process instead (add-ins
# load as usual) and attach to it via GetActiveObject.
$Excel = $null
try {
    $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
    Write-Host "Attached to running Excel."
} catch {
    Write-Host "Starting Excel as a normal process (so the Cap IQ XLL loads)..."
    Start-Process "excel.exe"
    $Deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 5
        try { $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application") } catch {}
    } while ($null -eq $Excel -and (Get-Date) -lt $Deadline)
    if ($null -eq $Excel) { throw "Could not attach to Excel after starting it." }
    Start-Sleep -Seconds 20   # let the S&P Cap IQ Pro add-in finish loading/signing in
}
$Excel.Visible = $true
$Excel.DisplayAlerts = $false

$Workbook = $null
foreach ($Wb in $Excel.Workbooks) {
    if ($Wb.FullName -eq $WorkbookPath) { $Workbook = $Wb; break }
}
if ($null -eq $Workbook) { $Workbook = $Excel.Workbooks.Open($WorkbookPath) }
Start-Sleep -Seconds 8   # give the add-in time to load with the workbook

# --- Formula sheet -----------------------------------------------------------------
$Headers = @("company_id", "period", "minority_interest", "preferred_equity",
             "lease_liabilities", "pension_liabilities", "cash_st_invest",
             "tangible_common_equity")
$Fields = @("IQ_PERIODDATE", "IQ_MINORITY_INTEREST", "IQ_PREF_EQUITY",
            "IQ_CAPITAL_LEASES", "IQ_PENSION", "IQ_CASH_ST_INVEST", "IQ_TBV")

$Sheet = $null
foreach ($S in $Workbook.Worksheets) { if ($S.Name -eq "evbridge_formula") { $Sheet = $S; break } }
if ($null -eq $Sheet) { $Sheet = $Workbook.Worksheets.Add(); $Sheet.Name = "evbridge_formula" }
$Sheet.Cells.Clear() | Out-Null
for ($i = 0; $i -lt $Headers.Count; $i++) { $Sheet.Cells.Item(1, $i + 1).Value2 = $Headers[$i] }
$Row = 2
foreach ($Id in $Universe) {
    $Sheet.Cells.Item($Row, 1).Value2 = $Id
    for ($i = 0; $i -lt $Fields.Count; $i++) {
        $Sheet.Cells.Item($Row, $i + 2).Formula = "=CIQ(""$Id"",""$($Fields[$i])"",""IQ_FQ"")"
    }
    $Row++
}
$Workbook.Save() | Out-Null
Write-Host "evbridge_formula sheet written: $($Universe.Count) rows x $($Fields.Count) fields"

# --- Refresh via ribbon (All Sheets) --------------------------------------------------
$Process = Get-Process EXCEL | Select-Object -First 1
$Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
$NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
$TabCondition = New-Object System.Windows.Automation.PropertyCondition($NameProperty, "S&P Cap IQ Pro")
$Tab = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $TabCondition)
if ($null -eq $Tab) { throw "S&P Cap IQ Pro ribbon tab not found - is the add-in loaded and signed in?" }
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
if ($null -eq $Refresh) { throw "Refresh Data control not found on the Cap IQ ribbon." }
$expanded = $false
try { $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null; $expanded = $true } catch {}
if (-not $expanded) { try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {} }
Start-Sleep -Milliseconds 800
$AllSheetsCondition = New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")
$AllSheets = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $AllSheetsCondition)
if ($null -eq $AllSheets) { throw "'All Sheets' refresh option not found - set Refresh Scope to 'Entire Workbook'." }
$AllSheets.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null
Write-Host "Refresh fired; polling..."

$Deadline = (Get-Date).AddSeconds(1500)
do {
    Start-Sleep -Seconds 8
    $Pending = 0
    $NameErr = 0
    foreach ($Cell in $Sheet.UsedRange.Cells) {
        $t = [string]$Cell.Text
        if ($t -eq "#PEND") { $Pending++ }
        elseif ($t -eq "#NAME?") { $NameErr++ }
    }
    Write-Host "evbridge pending=$Pending name_err=$NameErr"
} while ($Pending -gt 0 -and (Get-Date) -lt $Deadline)
if ($NameErr -gt ($Universe.Count * 2)) {
    throw "CIQ formulas returned #NAME? - the Capital IQ add-in is not loaded/signed in. Open Excel, sign in to S&P Capital IQ Pro, and rerun."
}
$Workbook.Save() | Out-Null

# --- Scrape ------------------------------------------------------------------------
function To-Double($Value) {
    if ($null -eq $Value) { return $null }
    $Text = ([string]$Value).Trim()
    if ($Text -eq "" -or $Text -like "#*" -or $Text -like "(*Invalid*") { return $null }
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

$Rows = @()
for ($Row = 2; $Row -le $Sheet.UsedRange.Rows.Count; $Row++) {
    $Id = [string]$Sheet.Cells.Item($Row, 1).Text
    if (-not $Id) { continue }
    $Rows += [PSCustomObject]@{
        company_id = $Id
        period = SerialToDate ([string]$Sheet.Cells.Item($Row, 2).Text)
        minority_interest = To-Double ([string]$Sheet.Cells.Item($Row, 3).Text)
        preferred_equity = To-Double ([string]$Sheet.Cells.Item($Row, 4).Text)
        lease_liabilities = To-Double ([string]$Sheet.Cells.Item($Row, 5).Text)
        pension_liabilities = To-Double ([string]$Sheet.Cells.Item($Row, 6).Text)
        cash_st_invest = To-Double ([string]$Sheet.Cells.Item($Row, 7).Text)
        tangible_common_equity = To-Double ([string]$Sheet.Cells.Item($Row, 8).Text)
    }
}
$PatchPath = Join-Path $OutDir "ev_bridge_patch.csv"
$Rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $PatchPath
Write-Host "Wrote $($Rows.Count) rows -> $PatchPath"
Write-Host "Next: python scripts\patch_ev_bridge_fields.py && rebuild the dataset."
