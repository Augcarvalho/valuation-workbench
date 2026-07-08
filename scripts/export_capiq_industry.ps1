# Capital IQ industry/country export for the whole universe (peer-scoring enrichment).
#
#   powershell -ExecutionPolicy Bypass -File scripts\export_capiq_industry.ps1
#
# Pulls IQ_PRIMARY_INDUSTRY and IQ_COUNTRY_NAME for every name in
# data_private\universe.csv (3 formulas per company - fast refresh) into
# data_private\capiq_exports\company_industry.csv. The peer-suggestion engine
# (src/modeling/peer_sets.py attach_industry) picks the file up automatically.
#
# Requires Excel OPEN with the Capital IQ add-in signed in.
# Output is licensed data and MUST stay inside data_private/ (gitignored).

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutPath = Join-Path $ProjectRoot "data_private\capiq_exports\company_industry.csv"
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
    $Sheet.Cells.Item(1, 2).Value2 = "primary_industry"
    $Sheet.Cells.Item(1, 3).Value2 = "country"
    $Sheet.Cells.Item(1, 4).Value2 = "company_status"
    $Row = 2
    foreach ($Company in $Universe) {
        $Id = $Company.id
        $Sheet.Cells.Item($Row, 1).Value2 = $Id
        $Sheet.Cells.Item($Row, 2).Formula = "=CIQ(""$Id"",""IQ_PRIMARY_INDUSTRY"")"
        $Sheet.Cells.Item($Row, 3).Formula = "=CIQ(""$Id"",""IQ_COUNTRY_NAME"")"
        $Sheet.Cells.Item($Row, 4).Formula = "=CIQ(""$Id"",""IQ_COMPANY_STATUS"")"
        $Row++
    }

    # Refresh via ribbon (All Sheets).
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

    $Deadline = (Get-Date).AddSeconds(300)
    do {
        Start-Sleep -Seconds 4
        $Pending = 0
        foreach ($Cell in $Sheet.UsedRange.Cells) {
            if ([string]$Cell.Text -eq "#PEND") { $Pending++ }
        }
        Write-Host "industry pending=$Pending"
    } while ($Pending -gt 0 -and (Get-Date) -lt $Deadline)

    $Rows = @()
    for ($Row = 2; $Row -le $Sheet.UsedRange.Rows.Count; $Row++) {
        $Id = [string]$Sheet.Cells.Item($Row, 1).Text
        if (-not $Id) { continue }
        $Industry = ([string]$Sheet.Cells.Item($Row, 2).Text).Trim()
        $Country = ([string]$Sheet.Cells.Item($Row, 3).Text).Trim()
        $Status = ([string]$Sheet.Cells.Item($Row, 4).Text).Trim()
        foreach ($Ref in [ref]$Industry, [ref]$Country, [ref]$Status) {
            if ($Ref.Value -like "#*" -or $Ref.Value -like "(*Invalid*" -or $Ref.Value -eq "NA") { $Ref.Value = "" }
        }
        $Rows += [PSCustomObject]@{
            company_id = $Id
            primary_industry = $Industry
            country = $Country
            company_status = $Status
        }
    }
    $Rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $OutPath
    Write-Host "Industry export complete: $($Rows.Count) companies -> $OutPath"
} catch {
    Write-Host "Industry export failed: $($_.Exception.Message)"
    exit 1
} finally {
    if ($null -ne $Workbook) { try { $Workbook.Close($false) | Out-Null } catch {} }
}
