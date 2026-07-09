# Refresh an already-built Capital IQ formula workbook, then scrape resolved values.
#
# This is used for larger private export universes where generating formulas via
# Excel COM cell-by-cell is too slow. Build the workbook first, open it here,
# refresh all CapIQ formulas through the S&P ribbon, then harvest the values with
# scrape_capiq_workbook.ps1.
#
# Outputs are licensed data and MUST stay inside data_private/ (gitignored).

param(
    [string]$WorkbookPath = "",
    [int]$TimeoutSeconds = 5400,
    [int]$PollSeconds = 15
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
if (-not $WorkbookPath) {
    $WorkbookPath = Join-Path $OutDir "capiq_watchlist_workbook.xlsx"
}
if (-not (Test-Path $WorkbookPath)) { throw "Workbook not found: $WorkbookPath" }

function Attach-Excel() {
    $Excel = $null
    try {
        $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
        Write-Host "Attached to running Excel."
    } catch {
        Write-Host "Starting Excel so the Capital IQ add-in loads normally..."
        Start-Process "excel.exe"
        $Deadline = (Get-Date).AddSeconds(90)
        do {
            Start-Sleep -Seconds 5
            try { $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application") } catch {}
        } while ($null -eq $Excel -and (Get-Date) -lt $Deadline)
        if ($null -eq $Excel) { throw "Could not attach to Excel." }
        Start-Sleep -Seconds 20
    }
    $Excel.Visible = $true
    $Excel.DisplayAlerts = $false
    return $Excel
}

function Get-Workbook($Excel, [string]$Path) {
    foreach ($Wb in $Excel.Workbooks) {
        if ($Wb.FullName -eq $Path) { return $Wb }
    }
    return $Excel.Workbooks.Open($Path)
}

function Invoke-CapIQRefreshAllSheets($Excel) {
    $Process = Get-Process EXCEL | Select-Object -First 1
    $Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty

    $Tab = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "S&P Cap IQ Pro")))
    if ($null -eq $Tab) { throw "S&P Cap IQ Pro ribbon tab not found. Is the add-in loaded and signed in?" }
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
    if ($null -eq $Refresh) { throw "Could not find the Capital IQ Refresh Data control." }

    $Expanded = $false
    try {
        $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null
        $Expanded = $true
    } catch {}
    if (-not $Expanded) {
        try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {}
    }
    Start-Sleep -Milliseconds 800

    $AllSheets = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")))
    if ($null -eq $AllSheets) {
        throw "Could not find 'All Sheets'. Set Refresh Scope to Entire Workbook in S&P Cap IQ Pro Settings."
    }
    $AllSheets.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null
}

function Count-Pending($Workbook) {
    $Pending = 0
    $NameLike = 0
    foreach ($Sheet in $Workbook.Worksheets) {
        if (-not ([string]$Sheet.Name).EndsWith("_formula")) { continue }
        $Values = $Sheet.UsedRange.Value2
        $Rows = $Sheet.UsedRange.Rows.Count
        $Cols = $Sheet.UsedRange.Columns.Count
        if ($Rows -eq 1 -and $Cols -eq 1) {
            $Text = [string]$Values
            if ($Text -eq "#PEND") { $Pending++ }
            if ($Text -eq "#NAME?") { $NameLike++ }
            continue
        }
        for ($r = 1; $r -le $Rows; $r++) {
            for ($c = 1; $c -le $Cols; $c++) {
                $Text = [string]$Values[$r, $c]
                if ($Text -eq "#PEND") { $Pending++ }
                if ($Text -eq "#NAME?") { $NameLike++ }
            }
        }
    }
    return @{ pending = $Pending; name_like = $NameLike }
}

function Save-WorkbookWithRetry($Workbook, [int]$Attempts = 12, [int]$SleepSeconds = 10) {
    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            $Workbook.Save() | Out-Null
            Write-Host "Workbook saved."
            return
        } catch {
            if ($i -eq $Attempts) { throw }
            Write-Host "Excel rejected Save() while the add-in was busy; retry $i/$Attempts..."
            Start-Sleep -Seconds $SleepSeconds
        }
    }
}

$RunStart = Get-Date
$Excel = Attach-Excel
$Workbook = Get-Workbook $Excel $WorkbookPath
$Workbook.Activate() | Out-Null
Start-Sleep -Seconds 10

Write-Host "Refreshing workbook: $($Workbook.Name)"
Invoke-CapIQRefreshAllSheets $Excel

$Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds $PollSeconds
    $Counts = Count-Pending $Workbook
    $Elapsed = [Math]::Round(((Get-Date) - $RunStart).TotalMinutes, 1)
    Write-Host "elapsed=${Elapsed}m pending=$($Counts.pending) name_like=$($Counts.name_like)"
} while ($Counts.pending -gt 0 -and (Get-Date) -lt $Deadline)

Save-WorkbookWithRetry $Workbook
Write-Host "Saved refreshed workbook. Running scrape..."

& (Join-Path $ProjectRoot "scripts\maintenance\scrape_capiq_workbook.ps1")

$Duration = [Math]::Round(((Get-Date) - $RunStart).TotalMinutes, 1)
Write-Host "Refresh + scrape complete in $Duration minutes."
