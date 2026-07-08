# Look up ONE company identifier through the Capital IQ Excel Add-In.
#
#   powershell -ExecutionPolicy Bypass -File scripts\lookup_capiq_company.ps1 -Id "BOVESPA:GMAT3"
#
# Requires Excel to be OPEN with the S&P Capital IQ Pro add-in signed in.
# Creates a throwaway workbook (never saved), writes one row of CIQ formulas,
# refreshes it, scrapes the result, and writes a JSON preview to
# data_private\capiq_exports\company_lookup.json.
#
# Invalid identifiers resolve to {"resolved": false, ...} - never an exception.

param(
    [Parameter(Mandatory = $true)][string]$Id
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutPath = Join-Path $OutDir "company_lookup.json"

function Write-Result($Object) {
    $Object | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 -Path $OutPath
    Write-Host ($Object | ConvertTo-Json -Depth 3 -Compress)
}

try {
    $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
} catch {
    Write-Result @{ company_id = $Id; resolved = $false; error = "Excel is not open. Open Excel with the Capital IQ add-in signed in and retry." }
    exit 0
}

$Workbook = $null
try {
    $Excel.DisplayAlerts = $false
    $Workbook = $Excel.Workbooks.Add()
    $Sheet = $Workbook.Worksheets.Item(1)

    $Sheet.Cells.Item(1, 1).Value2 = $Id
    $Sheet.Cells.Item(1, 2).Formula = "=CIQ(""$Id"",""IQ_COMPANY_NAME"")"
    $Sheet.Cells.Item(1, 3).Formula = "=CIQ(""$Id"",""IQ_EXCHANGE"")"
    $Sheet.Cells.Item(1, 4).Formula = "=CIQ(""$Id"",""IQ_INDUSTRY"")"
    $Sheet.Cells.Item(1, 5).Formula = "=CIQ(""$Id"",""IQ_FILING_CURRENCY"")"

    # Refresh via the ribbon dropdown -> "All Sheets" (scope-independent).
    $Process = Get-Process EXCEL | Select-Object -First 1
    $Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
    $TabCondition = New-Object System.Windows.Automation.PropertyCondition($NameProperty, "S&P Cap IQ Pro")
    $Tab = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $TabCondition)
    if ($null -ne $Tab) {
        try { $Tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() | Out-Null } catch {}
    }
    Start-Sleep -Milliseconds 600

    $Refresh = $null
    foreach ($Element in $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
        $ct = $Element.Current.ControlType.ProgrammaticName
        if ($Element.Current.Name -eq "Refresh Data" -and ($ct -eq "ControlType.SplitButton" -or $ct -eq "ControlType.Button")) {
            $Refresh = $Element
            if ($ct -eq "ControlType.SplitButton") { break }
        }
    }
    if ($null -eq $Refresh) { throw "Capital IQ Refresh control not found - is the add-in loaded?" }
    $expanded = $false
    try { $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null; $expanded = $true } catch {}
    if (-not $expanded) {
        try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {}
    }
    Start-Sleep -Milliseconds 800
    $AllSheetsCondition = New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")
    $AllSheets = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $AllSheetsCondition)
    if ($null -ne $AllSheets) {
        $AllSheets.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null
    }

    # Poll until resolved or timeout (small sheet -> fast).
    $Deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 3
        $NameText = [string]$Sheet.Cells.Item(1, 2).Text
    } while ($NameText -eq "#PEND" -and (Get-Date) -lt $Deadline)

    function Clean($Value) {
        $t = ([string]$Value).Trim()
        if ($t -like "#*" -or $t -like "(*Invalid*" -or $t -eq "NA") { return $null }
        return $t
    }

    $Name = Clean $Sheet.Cells.Item(1, 2).Text
    $Result = @{
        company_id = $Id
        resolved = [bool]$Name
        company_name = $Name
        exchange = Clean $Sheet.Cells.Item(1, 3).Text
        industry = Clean $Sheet.Cells.Item(1, 4).Text
        currency = Clean $Sheet.Cells.Item(1, 5).Text
        error = if ($Name) { "" } elseif ($NameText -eq "#PEND") { "Capital IQ did not respond within 90s - check the add-in sign-in." } else { "Identifier did not resolve in Capital IQ." }
        looked_up_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }
    Write-Result $Result
} catch {
    Write-Result @{ company_id = $Id; resolved = $false; error = $_.Exception.Message }
} finally {
    if ($null -ne $Workbook) {
        try { $Workbook.Close($false) | Out-Null } catch {}
    }
}
