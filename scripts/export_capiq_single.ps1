# Targeted Capital IQ export for ONE company (used by Add Company auto-fetch).
#
#   powershell -ExecutionPolicy Bypass -File scripts\export_capiq_single.ps1 -Id "BOVESPA:GMAT3" -Sector "Brazil Retail" -Currency BRL
#
# Mirrors the five sheets of export_capiq_watchlist.ps1 (companies, quarterly
# financials, market snapshot, monthly valuation history, consensus estimates)
# for a single identifier, in a throwaway workbook. Output goes to an isolated
# staging folder:
#
#   data_private\capiq_exports\staging_single\<ID with : -> _>\*.csv
#
# The main export CSVs are NEVER touched here - src/ingestion/single_import.py
# validates the staging output and upserts it into the main CSVs, so a failed
# or partial fetch cannot corrupt good data.
#
# Requires Excel OPEN with the Capital IQ add-in signed in.
# All outputs are licensed data and MUST stay inside data_private/ (gitignored).

param(
    [Parameter(Mandatory=$true)][string]$Id,
    [string]$Ticker = "",
    [string]$Sector = "Unclassified",
    [string]$Currency = "USD"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SafeId = $Id -replace ":", "_"
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports\staging_single\$SafeId"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ResultPath = Join-Path $OutDir "staging_result.json"

if (-not $Ticker) { $Ticker = ($Id -split ":")[-1] }

$QuarterCount = 20
$ValuationMonths = 36
$RunStart = Get-Date

function Write-FailureResult([string]$Message) {
    @{ ok = $false; company_id = $Id; error = $Message } | ConvertTo-Json | Set-Content -Encoding UTF8 $ResultPath
    Write-Host "Single export failed: $Message"
}

try {
    $Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
} catch {
    Write-FailureResult "Excel is not open (Capital IQ add-in requires a signed-in Excel session)."
    exit 1
}

$Periods = @(0..($QuarterCount - 1) | ForEach-Object { if ($_ -eq 0) { "IQ_FQ" } else { "IQ_FQ-$_" } })
$MonthEnds = @(0..($ValuationMonths - 1) | ForEach-Object {
    (Get-Date -Day 1).AddMonths(-$_).AddDays(-1).ToString("MM/dd/yyyy")
})
$Date30 = (Get-Date).AddDays(-30).ToString("MM/dd/yyyy")
$Date90 = (Get-Date).AddDays(-90).ToString("MM/dd/yyyy")

# --- Helpers (same semantics as export_capiq_watchlist.ps1) -----------------------

function Set-Headers($Sheet, [string[]]$Headers) {
    for ($Index = 0; $Index -lt $Headers.Count; $Index++) {
        $Sheet.Cells.Item(1, $Index + 1).Value2 = $Headers[$Index]
    }
}

function Invoke-CapIQRefreshAllSheets($Root) {
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
    if ($null -eq $Refresh) { throw "Could not find the 'Refresh Data' ribbon control." }
    $done = $false
    try { $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null; $done = $true } catch {}
    if (-not $done) { try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {} }
    Start-Sleep -Milliseconds 800
    $NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
    $All = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")))
    if ($null -eq $All) {
        throw "Could not find the 'All Sheets' refresh option. Set Refresh Scope to 'Entire Workbook' in S&P Cap IQ Pro Settings and rerun."
    }
    $All.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null
}

function Wait-Pending($Sheet, [int]$TimeoutSeconds) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 3
        $Pending = 0
        foreach ($Cell in $Sheet.UsedRange.Cells) {
            if ([string]$Cell.Text -eq "#PEND") { $Pending++ }
        }
        Write-Host "$($Sheet.Name) pending=$Pending"
    } while ($Pending -gt 0 -and (Get-Date) -lt $Deadline)
    return $Pending
}

function Get-HeaderMap($Sheet) {
    $Map = @{}
    for ($Column = 1; $Column -le $Sheet.UsedRange.Columns.Count; $Column++) {
        $Name = [string]$Sheet.Cells.Item(1, $Column).Text
        if ($Name) { $Map[$Name] = $Column }
    }
    return $Map
}

function Get-CellText($Sheet, $Row, $Map, $Name) {
    if (-not $Map.ContainsKey($Name)) { return $null }
    return [string]$Sheet.Cells.Item($Row, $Map[$Name]).Text
}

function To-Double($Value) {
    if (-not $Value -or $Value -like "#*" -or $Value -like "(*Invalid*" -or $Value -eq "NA") { return $null }
    $Parsed = 0.0
    if ([double]::TryParse(($Value -replace "[,%x]", ""), [ref]$Parsed)) { return $Parsed }
    return $null
}

function ExcelSerialToDateString($Value) {
    $Parsed = 0.0
    if ([double]::TryParse($Value, [ref]$Parsed) -and $Parsed -gt 20000) {
        return ([DateTime]::FromOADate($Parsed)).ToString("yyyy-MM-dd")
    }
    $ParsedDate = [DateTime]::MinValue
    if ([DateTime]::TryParse($Value, [ref]$ParsedDate)) { return $ParsedDate.ToString("yyyy-MM-dd") }
    return $null
}

function TextToDateString($Value) {
    $ParsedDate = [DateTime]::MinValue
    if ([DateTime]::TryParse($Value, [ref]$ParsedDate)) { return $ParsedDate.ToString("yyyy-MM-dd") }
    $Parsed = 0.0
    if ([double]::TryParse($Value, [ref]$Parsed) -and $Parsed -gt 20000) {
        return ([DateTime]::FromOADate($Parsed)).ToString("yyyy-MM-dd")
    }
    return $null
}

$Workbook = $null
try {
    $Excel.DisplayAlerts = $false
    $Workbook = $Excel.Workbooks.Add()

    # --- Sheet 1: companies ------------------------------------------------------
    $CompaniesSheet = $Workbook.Worksheets.Item(1)
    $CompaniesSheet.Name = "companies_formula"
    Set-Headers $CompaniesSheet @("company_id", "ticker", "company_name", "sector_capiq", "sector", "exchange", "currency", "source")
    $CompaniesSheet.Cells.Item(2, 1).Value2 = $Id
    $CompaniesSheet.Cells.Item(2, 2).Value2 = $Ticker
    $CompaniesSheet.Cells.Item(2, 3).Formula = "=CIQ(""$Id"",""IQ_COMPANY_NAME"")"
    $CompaniesSheet.Cells.Item(2, 4).Formula = "=CIQ(""$Id"",""IQ_INDUSTRY"")"
    $CompaniesSheet.Cells.Item(2, 5).Value2 = $Sector
    $CompaniesSheet.Cells.Item(2, 6).Formula = "=CIQ(""$Id"",""IQ_EXCHANGE"")"
    $CompaniesSheet.Cells.Item(2, 7).Value2 = $Currency
    $CompaniesSheet.Cells.Item(2, 8).Value2 = "Capital IQ Pro Excel Add-In"

    # --- Sheet 2: quarterly financials --------------------------------------------
    $FinancialsSheet = $Workbook.Worksheets.Add()
    $FinancialsSheet.Name = "financials_formula"
    Set-Headers $FinancialsSheet @(
        "company_id", "period_code", "period", "revenue", "gross_profit", "ebitda", "ebit",
        "net_income", "cfo", "capex_raw", "cash", "total_debt", "net_debt",
        "current_assets", "current_liabilities", "interest_expense_raw",
        "d_and_a", "sbc", "dividends_paid_raw", "buybacks_raw", "shares_diluted",
        "total_assets", "total_equity", "goodwill", "ar", "inventory", "ap"
    )
    $Fields = @(
        "IQ_PERIODDATE", "IQ_TOTAL_REV", "IQ_GP", "IQ_EBITDA", "IQ_EBIT", "IQ_NET_INC",
        "IQ_CASH_OPER", "IQ_CAPEX", "IQ_CASH_EQUIV", "IQ_TOTAL_DEBT", "IQ_NET_DEBT",
        "IQ_TOTAL_CURRENT_ASSETS", "IQ_TOTAL_CURRENT_LIAB", "IQ_INTEREST_EXP",
        "IQ_DA", "IQ_STOCK_BASED_COMP", "IQ_COMMON_DIV_CF", "IQ_COMMON_REP",
        "IQ_DILUT_WEIGHT", "IQ_TOTAL_ASSETS", "IQ_TOTAL_EQUITY", "IQ_GW",
        "IQ_AR", "IQ_INVENTORY", "IQ_AP"
    )
    $Row = 2
    foreach ($Period in $Periods) {
        $FinancialsSheet.Cells.Item($Row, 1).Value2 = $Id
        $FinancialsSheet.Cells.Item($Row, 2).Value2 = $Period
        for ($Index = 0; $Index -lt $Fields.Count; $Index++) {
            $FinancialsSheet.Cells.Item($Row, $Index + 3).Formula = "=CIQ(""$Id"",""$($Fields[$Index])"",""$Period"")"
        }
        $Row++
    }

    # --- Sheet 3: market snapshot ---------------------------------------------------
    $MarketSheet = $Workbook.Worksheets.Add()
    $MarketSheet.Name = "market_formula"
    Set-Headers $MarketSheet @("company_id", "share_price", "shares_outstanding", "market_cap", "enterprise_value")
    $MarketSheet.Cells.Item(2, 1).Value2 = $Id
    $MarketSheet.Cells.Item(2, 2).Formula = "=CIQ(""$Id"",""IQ_CLOSEPRICE"")"
    $MarketSheet.Cells.Item(2, 3).Formula = "=CIQ(""$Id"",""IQ_SHARESOUTSTANDING"")"
    $MarketSheet.Cells.Item(2, 4).Formula = "=CIQ(""$Id"",""IQ_MARKETCAP"")"
    $MarketSheet.Cells.Item(2, 5).Formula = "=CIQ(""$Id"",""IQ_ENTERPRISE_VALUE"")"

    # --- Sheet 4: monthly valuation history -------------------------------------------
    $ValuationSheet = $Workbook.Worksheets.Add()
    $ValuationSheet.Name = "valuation_formula"
    Set-Headers $ValuationSheet @(
        "company_id", "date", "share_price", "market_cap", "enterprise_value",
        "ev_to_ebitda_ltm", "ev_to_revenue_ltm", "pe_ltm"
    )
    $Row = 2
    foreach ($MonthEnd in $MonthEnds) {
        $ValuationSheet.Cells.Item($Row, 1).Value2 = $Id
        $ValuationSheet.Cells.Item($Row, 2).Value2 = $MonthEnd
        $ValuationSheet.Cells.Item($Row, 3).Formula = "=CIQ(""$Id"",""IQ_CLOSEPRICE"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 4).Formula = "=CIQ(""$Id"",""IQ_MARKETCAP"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 5).Formula = "=CIQ(""$Id"",""IQ_TEV"",""$MonthEnd"")"
        # Multiples: period ("IQ_LTM") in the 3rd slot, as-of date in the 4th.
        $ValuationSheet.Cells.Item($Row, 6).Formula = "=CIQ(""$Id"",""IQ_TEV_EBITDA"",""IQ_LTM"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 7).Formula = "=CIQ(""$Id"",""IQ_TEV_TOTAL_REV"",""IQ_LTM"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 8).Formula = "=CIQ(""$Id"",""IQ_PE_EXCL"",""IQ_LTM"",""$MonthEnd"")"
        $Row++
    }

    # --- Sheet 5: consensus estimates ----------------------------------------------------
    $EstimatesSheet = $Workbook.Worksheets.Add()
    $EstimatesSheet.Name = "estimates_formula"
    Set-Headers $EstimatesSheet @(
        "company_id", "revenue_consensus", "ebitda_consensus", "eps_consensus",
        "revenue_est_ntm", "ebitda_est_ntm", "eps_est_ntm", "num_analysts",
        "revenue_est_ntm_30d_ago", "eps_est_ntm_30d_ago",
        "revenue_est_ntm_90d_ago", "eps_est_ntm_90d_ago", "next_earnings_date"
    )
    $EstimatesSheet.Cells.Item(2, 1).Value2 = $Id
    $EstimatesSheet.Cells.Item(2, 2).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_FQ"")"
    $EstimatesSheet.Cells.Item(2, 3).Formula = "=CIQ(""$Id"",""IQ_EBITDA_EST"",""IQ_FQ"")"
    $EstimatesSheet.Cells.Item(2, 4).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_FQ"")"
    $EstimatesSheet.Cells.Item(2, 5).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item(2, 6).Formula = "=CIQ(""$Id"",""IQ_EBITDA_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item(2, 7).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item(2, 8).Formula = "=CIQ(""$Id"",""IQ_REVENUE_NUM_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item(2, 9).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_NTM"",""$Date30"")"
    $EstimatesSheet.Cells.Item(2, 10).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_NTM"",""$Date30"")"
    $EstimatesSheet.Cells.Item(2, 11).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_NTM"",""$Date90"")"
    $EstimatesSheet.Cells.Item(2, 12).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_NTM"",""$Date90"")"
    $EstimatesSheet.Cells.Item(2, 13).Formula = "=CIQ(""$Id"",""IQ_NEXT_EARNINGS_DATE"")"

    # --- Refresh (single workbook-wide pass) -------------------------------------------
    $Process = Get-Process EXCEL | Select-Object -First 1
    $Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    Invoke-CapIQRefreshAllSheets $Root
    $PendingCompanies = Wait-Pending $CompaniesSheet 180
    $PendingFinancials = Wait-Pending $FinancialsSheet 420
    $PendingMarket = Wait-Pending $MarketSheet 120
    $PendingValuation = Wait-Pending $ValuationSheet 420
    $PendingEstimates = Wait-Pending $EstimatesSheet 180

    # --- Scrape: companies ---------------------------------------------------------------
    $CompaniesMap = Get-HeaderMap $CompaniesSheet
    $Name = Get-CellText $CompaniesSheet 2 $CompaniesMap "company_name"
    if (-not $Name -or $Name -like "(*Invalid*" -or $Name -like "#*") {
        Write-FailureResult "Capital IQ did not resolve '$Id' (company name came back '$Name')."
        exit 1
    }
    $Companies = @([PSCustomObject]@{
        company_id = $Id
        ticker = $Ticker
        company_name = $Name
        sector = $Sector
        exchange = Get-CellText $CompaniesSheet 2 $CompaniesMap "exchange"
        currency = $Currency
        source = "Capital IQ Pro Excel Add-In"
    })
    $Companies | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "companies.csv")

    # --- Scrape: financials ----------------------------------------------------------------
    $FinancialsMap = Get-HeaderMap $FinancialsSheet
    $Financials = @()
    for ($Row = 2; $Row -le $FinancialsSheet.UsedRange.Rows.Count; $Row++) {
        $RowId = Get-CellText $FinancialsSheet $Row $FinancialsMap "company_id"
        if (-not $RowId) { continue }
        $Period = ExcelSerialToDateString (Get-CellText $FinancialsSheet $Row $FinancialsMap "period")
        if (-not $Period) { continue }
        $Cfo = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "cfo")
        $CapexRaw = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "capex_raw")
        $Capex = if ($null -ne $CapexRaw) { [Math]::Abs($CapexRaw) } else { $null }
        $CurrentAssets = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "current_assets")
        $CurrentLiabilities = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "current_liabilities")
        $WorkingCapital = if ($null -ne $CurrentAssets -and $null -ne $CurrentLiabilities) { $CurrentAssets - $CurrentLiabilities } else { $null }
        $InterestRaw = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "interest_expense_raw")
        $InterestExpense = if ($null -ne $InterestRaw) { [Math]::Abs($InterestRaw) } else { $null }
        $DividendsRaw = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "dividends_paid_raw")
        $Dividends = if ($null -ne $DividendsRaw) { [Math]::Abs($DividendsRaw) } else { $null }
        $BuybacksRaw = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "buybacks_raw")
        $Buybacks = if ($null -ne $BuybacksRaw) { [Math]::Abs($BuybacksRaw) } else { $null }
        $Financials += [PSCustomObject]@{
            company_id = $RowId
            period = $Period
            revenue = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "revenue")
            gross_profit = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "gross_profit")
            ebitda = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "ebitda")
            ebit = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "ebit")
            net_income = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "net_income")
            cfo = $Cfo
            capex = $Capex
            fcf = if ($null -ne $Cfo -and $null -ne $Capex) { $Cfo - $Capex } else { $null }
            cash = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "cash")
            total_debt = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "total_debt")
            net_debt = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "net_debt")
            working_capital = $WorkingCapital
            interest_expense = $InterestExpense
            d_and_a = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "d_and_a")
            sbc = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "sbc")
            dividends_paid = $Dividends
            buybacks = $Buybacks
            shares_diluted = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "shares_diluted")
            total_assets = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "total_assets")
            total_equity = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "total_equity")
            goodwill = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "goodwill")
            ar = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "ar")
            inventory = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "inventory")
            ap = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "ap")
            source = "Capital IQ Pro Excel Add-In"
        }
    }
    $Financials | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "financials_quarterly.csv")

    $LatestPeriod = $null
    if ($Financials.Count -gt 0) {
        $LatestPeriod = ($Financials | Sort-Object period -Descending | Select-Object -First 1).period
    }

    # --- Scrape: market snapshot -----------------------------------------------------------
    $MarketMap = Get-HeaderMap $MarketSheet
    $Market = @()
    if ($null -ne $LatestPeriod) {
        $SharesRaw = To-Double (Get-CellText $MarketSheet 2 $MarketMap "shares_outstanding")
        $Market += [PSCustomObject]@{
            company_id = $Id
            period = $LatestPeriod
            share_price = To-Double (Get-CellText $MarketSheet 2 $MarketMap "share_price")
            shares_outstanding = if ($null -ne $SharesRaw) { [Math]::Round($SharesRaw * 1000000, 0) } else { $null }
            market_cap = To-Double (Get-CellText $MarketSheet 2 $MarketMap "market_cap")
            enterprise_value = To-Double (Get-CellText $MarketSheet 2 $MarketMap "enterprise_value")
            source = "Capital IQ Pro Excel Add-In"
        }
    }
    $Market | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "market_data.csv")

    # --- Scrape: valuation history ----------------------------------------------------------
    $ValuationMap = Get-HeaderMap $ValuationSheet
    $Valuation = @()
    for ($Row = 2; $Row -le $ValuationSheet.UsedRange.Rows.Count; $Row++) {
        $RowId = Get-CellText $ValuationSheet $Row $ValuationMap "company_id"
        if (-not $RowId) { continue }
        $DateText = TextToDateString (Get-CellText $ValuationSheet $Row $ValuationMap "date")
        if (-not $DateText) { continue }
        $Price = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "share_price")
        if ($null -eq $Price) { continue }
        $Valuation += [PSCustomObject]@{
            company_id = $RowId
            date = $DateText
            share_price = $Price
            market_cap = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "market_cap")
            enterprise_value = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "enterprise_value")
            ev_to_ebitda_ltm = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "ev_to_ebitda_ltm")
            ev_to_revenue_ltm = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "ev_to_revenue_ltm")
            pe_ltm = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "pe_ltm")
            source = "Capital IQ Pro Excel Add-In"
        }
    }
    $Valuation | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "valuation_history.csv")

    # --- Scrape: estimates --------------------------------------------------------------------
    $EstimatesMap = Get-HeaderMap $EstimatesSheet
    $Estimates = @()
    if ($null -ne $LatestPeriod) {
        $Estimates += [PSCustomObject]@{
            company_id = $Id
            period = $LatestPeriod
            revenue_consensus = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "revenue_consensus")
            ebitda_consensus = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "ebitda_consensus")
            eps_consensus = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "eps_consensus")
            guidance_low = $null
            guidance_high = $null
            revenue_est_ntm = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "revenue_est_ntm")
            ebitda_est_ntm = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "ebitda_est_ntm")
            eps_est_ntm = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "eps_est_ntm")
            num_analysts = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "num_analysts")
            revenue_est_ntm_30d_ago = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "revenue_est_ntm_30d_ago")
            eps_est_ntm_30d_ago = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "eps_est_ntm_30d_ago")
            revenue_est_ntm_90d_ago = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "revenue_est_ntm_90d_ago")
            eps_est_ntm_90d_ago = To-Double (Get-CellText $EstimatesSheet 2 $EstimatesMap "eps_est_ntm_90d_ago")
            next_earnings_date = TextToDateString (Get-CellText $EstimatesSheet 2 $EstimatesMap "next_earnings_date")
            source = "Capital IQ Pro Excel Add-In"
        }
    }
    $Estimates | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "estimates.csv")

    @{
        ok = $true
        company_id = $Id
        company_name = $Name
        exported_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        duration_minutes = [Math]::Round(((Get-Date) - $RunStart).TotalMinutes, 1)
        financial_rows = $Financials.Count
        market_rows = $Market.Count
        valuation_rows = $Valuation.Count
        estimate_rows = $Estimates.Count
        pending = @{
            companies = $PendingCompanies; financials = $PendingFinancials
            market = $PendingMarket; valuation = $PendingValuation; estimates = $PendingEstimates
        }
    } | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $ResultPath
    Write-Host "Single export complete: $Name -> $OutDir (financials=$($Financials.Count) valuation=$($Valuation.Count))"
} catch {
    Write-FailureResult $_.Exception.Message
    exit 1
} finally {
    if ($null -ne $Workbook) { try { $Workbook.Close($false) | Out-Null } catch {} }
}
