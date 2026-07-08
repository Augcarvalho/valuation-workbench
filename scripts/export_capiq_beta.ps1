# Capital IQ beta export for the whole universe (WACC input).
#
#   powershell -ExecutionPolicy Bypass -File scripts\export_capiq_beta.ps1
#
# Pulls 2-year and 5-year levered betas for every name in data_private\universe.csv
# into data_private\capiq_exports\company_beta.csv. The dataset build joins it onto
# market data (beta_2y / beta_5y) and the WACC engine stops using the default 1.0.
#
# Requires Excel OPEN with the Capital IQ add-in signed in.
# Output is licensed data and MUST stay inside data_private/ (gitignored).

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutPath = Join-Path $ProjectRoot "data_private\capiq_exports\company_beta.csv"
$UniverseCsv = Join-Path $ProjectRoot "data_private\universe.csv"
if (-not (Test-Path $UniverseCsv)) { throw "Universe file not found: $UniverseCsv" }
$Universe = @(Import-Csv $UniverseCsv)

try {
    $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
} catch {
    Write-Host "Excel is not open - aborting."
    exit 1
}

$Workbook = $null
try {
    $Excel.DisplayAlerts = $false
    $Workbook = $Excel.Workbooks.Add()
    $Sheet = $Workbook.Worksheets.Item(1)
    $Sheet.Cells.Item(1, 1).Value2 = "company_id"
    $Sheet.Cells.Item(1, 2).Value2 = "beta_2y"
    $Sheet.Cells.Item(1, 3).Value2 = "beta_5y"
    $Row = 2
    foreach ($Company in $Universe) {
        $Id = $Company.id
        $Sheet.Cells.Item($Row, 1).Value2 = $Id
        $Sheet.Cells.Item($Row, 2).Formula = "=CIQ(""$Id"",""IQ_BETA_2YR"")"
        $Sheet.Cells.Item($Row, 3).Formula = "=CIQ(""$Id"",""IQ_BETA_5YR"")"
        $Row++
    }

    $Process = Get-Process EXCEL | Select-Object -First 1
    $Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
    $Tab = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "S&P Cap IQ Pro")))
    if ($null -ne $Tab) { try { $Tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() | Out-Null } catch {} }
    Start-Sleep -Milliseconds 600
    $Refresh = $null
    foreach ($El in $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
        $ct = $El.Current.ControlType.ProgrammaticName
        if ($El.Current.Name -eq "Refresh Data" -and ($ct -eq "ControlType.SplitButton" -or $ct -eq "ControlType.Button")) {
            $Refresh = $El
            if ($ct -eq "ControlType.SplitButton") { break }
        }
    }
    if ($null -ne $Refresh) {
        $done = $false
        try { $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null; $done = $true } catch {}
        if (-not $done) { try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {} }
        Start-Sleep -Milliseconds 800
        $All = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
            (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")))
        if ($null -ne $All) { $All.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null }
    }

    $Deadline = (Get-Date).AddSeconds(240)
    do {
        Start-Sleep -Seconds 4
        $Pending = 0
        foreach ($Cell in $Sheet.UsedRange.Cells) {
            if ([string]$Cell.Text -eq "#PEND") { $Pending++ }
        }
        Write-Host "beta pending=$Pending"
    } while ($Pending -gt 0 -and (Get-Date) -lt $Deadline)

    function CleanNum([string]$v) {
        if (-not $v -or $v -like "#*" -or $v -like "(*Invalid*" -or $v -eq "NA") { return "" }
        $p = 0.0
        if ([double]::TryParse($v, [ref]$p)) { return $p }
        return ""
    }

    $Rows = @()
    for ($Row = 2; $Row -le $Sheet.UsedRange.Rows.Count; $Row++) {
        $Id = [string]$Sheet.Cells.Item($Row, 1).Text
        if (-not $Id) { continue }
        $Rows += [PSCustomObject]@{
            company_id = $Id
            beta_2y = CleanNum ([string]$Sheet.Cells.Item($Row, 2).Text)
            beta_5y = CleanNum ([string]$Sheet.Cells.Item($Row, 3).Text)
        }
    }
    $Rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $OutPath
    $With2y = @($Rows | Where-Object { $_.beta_2y -ne "" }).Count
    Write-Host "Beta export complete: $($Rows.Count) companies ($With2y with beta_2y) -> $OutPath"
} catch {
    Write-Host "Beta export failed: $($_.Exception.Message)"
    exit 1
} finally {
    if ($null -ne $Workbook) { try { $Workbook.Close($false) | Out-Null } catch {} }
}
