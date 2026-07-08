# Probe which peer/comp-related Capital IQ mnemonics resolve on THIS entitlement.
#
#   powershell -ExecutionPolicy Bypass -File scripts\probe_capiq_peers.ps1
#
# Requires Excel OPEN with the Capital IQ add-in signed in. Writes candidate
# formulas for one liquid test name (NYSE:NKE) into a throwaway workbook,
# refreshes, and reports which candidates return data vs errors. Results go to
# data_private\capiq_exports\peer_probe_results.json.
#
# If any QUICK-COMPS/RELATED mnemonic resolves, wire it into the peer-suggestion
# pipeline as the preferred source (see src/modeling/peer_sets.py hierarchy).

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutPath = Join-Path $OutDir "peer_probe_results.json"

$TestId = "NYSE:NKE"

# Candidates: peer/related extraction + attribute fields for richer scoring.
$Candidates = @(
    @{ name = "quick_comps";        formula = "=CIQ(""$TestId"",""IQ_QUICK_COMPS"")" },
    @{ name = "comp_set";           formula = "=CIQ(""$TestId"",""IQ_COMP_SET"")" },
    @{ name = "competitor_name";    formula = "=CIQ(""$TestId"",""IQ_COMPETITOR_NAME"",1)" },
    @{ name = "competitor_list";    formula = "=CIQ(""$TestId"",""IQ_COMPETITOR"")" },
    @{ name = "peers";              formula = "=CIQ(""$TestId"",""IQ_PEERS"")" },
    @{ name = "gics_sector";        formula = "=CIQ(""$TestId"",""IQ_GICS_SECTOR"")" },
    @{ name = "gics_code";          formula = "=CIQ(""$TestId"",""IQ_GICS"")" },
    @{ name = "sub_industry";       formula = "=CIQ(""$TestId"",""IQ_SUB_INDUSTRY"")" },
    @{ name = "primary_industry";   formula = "=CIQ(""$TestId"",""IQ_PRIMARY_INDUSTRY"")" },
    @{ name = "sic_code";           formula = "=CIQ(""$TestId"",""IQ_SIC_CODE"")" },
    @{ name = "naics_code";         formula = "=CIQ(""$TestId"",""IQ_NAICS_CODE"")" },
    @{ name = "country";            formula = "=CIQ(""$TestId"",""IQ_COUNTRY_NAME"")" },
    @{ name = "business_desc";      formula = "=CIQ(""$TestId"",""IQ_BUSINESS_DESCRIPTION"")" },
    @{ name = "company_status";     formula = "=CIQ(""$TestId"",""IQ_COMPANY_STATUS"")" },
    @{ name = "avg_daily_value";    formula = "=CIQ(""$TestId"",""IQ_AVG_DAILY_VALUE_TRADED_3MO"")" },
    @{ name = "avg_volume";         formula = "=CIQ(""$TestId"",""IQ_AVG_VOLUME_3MO"")" }
)

try {
    $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
} catch {
    @{ probed = $false; error = "Excel is not open." } | ConvertTo-Json | Set-Content -Encoding UTF8 $OutPath
    Write-Host "Excel is not open - probe aborted."
    exit 0
}

$Workbook = $null
try {
    $Excel.DisplayAlerts = $false
    $Workbook = $Excel.Workbooks.Add()
    $Sheet = $Workbook.Worksheets.Item(1)
    for ($i = 0; $i -lt $Candidates.Count; $i++) {
        $Sheet.Cells.Item($i + 1, 1).Value2 = $Candidates[$i].name
        $Sheet.Cells.Item($i + 1, 2).Formula = $Candidates[$i].formula
    }

    # Refresh via ribbon (All Sheets on the throwaway workbook).
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

    $Deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Seconds 4
        $Pending = 0
        for ($i = 1; $i -le $Candidates.Count; $i++) {
            if ([string]$Sheet.Cells.Item($i, 2).Text -eq "#PEND") { $Pending++ }
        }
    } while ($Pending -gt 0 -and (Get-Date) -lt $Deadline)

    $Results = @{}
    for ($i = 0; $i -lt $Candidates.Count; $i++) {
        $text = ([string]$Sheet.Cells.Item($i + 1, 2).Text).Trim()
        $ok = $text -and $text -notlike "#*" -and $text -notlike "(*Invalid*" -and $text -ne "NA"
        $Results[$Candidates[$i].name] = @{ resolved = $ok; value = $text.Substring(0, [Math]::Min(120, $text.Length)) }
    }
    @{ probed = $true; test_id = $TestId; probed_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"); results = $Results } |
        ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $OutPath
    Write-Host "Probe complete -> $OutPath"
    foreach ($k in $Results.Keys) {
        Write-Host ("{0,-20} {1}  {2}" -f $k, $Results[$k].resolved, $Results[$k].value)
    }
} catch {
    @{ probed = $false; error = $_.Exception.Message } | ConvertTo-Json | Set-Content -Encoding UTF8 $OutPath
    Write-Host "Probe failed: $($_.Exception.Message)"
} finally {
    if ($null -ne $Workbook) { try { $Workbook.Close($false) | Out-Null } catch {} }
}
