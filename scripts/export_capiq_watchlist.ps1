# Capital IQ watchlist export (V2).
#
# Drives the S&P Capital IQ Pro Excel Add-In through COM + UI Automation:
# writes CIQ() formula sheets, clicks the ribbon Refresh, polls #PEND cells,
# then scrapes typed values into private CSVs under data_private/capiq_exports.
#
# V2 additions:
#   - 20 quarters of financial history (was 8)
#   - deep-dive fields: D&A, SBC, dividends, buybacks, diluted shares,
#     total assets/equity, goodwill, AR, inventory, AP
#   - monthly valuation history sheet (price, market cap, EV, EV/EBITDA,
#     EV/Revenue, P/E) for the trailing $ValuationMonths months
#   - consensus estimates sheet (current quarter + NTM, with 30d/90d-ago
#     as-of snapshots for revision momentum) and next earnings date
#   - refresh_log.csv appended on every run
#   - universe read from data_private\universe.csv (columns: id,ticker,
#     sector,currency) - the watchlist composition is never committed
#
# NOTE ON MNEMONICS: field mnemonics vary slightly by CIQ entitlement/version.
# Any formula the add-in rejects resolves to an error cell, which the parser
# converts to null — the Python pipeline degrades gracefully for missing
# fields. Verify questionable mnemonics in Excel with a single CIQ() call.
#
# All outputs are licensed data and MUST stay inside data_private/ (gitignored).

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$QuarterCount = 20          # fiscal quarters of financial history
$ValuationMonths = 36       # months of valuation history
$RunStart = Get-Date

$Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
$Excel.DisplayAlerts = $false
$Workbook = $Excel.ActiveWorkbook
if ($null -eq $Workbook) {
    $Workbook = $Excel.Workbooks.Add()
}

$WorkbookPath = Join-Path $OutDir "capiq_watchlist_workbook.xlsx"

# --- Universe -----------------------------------------------------------------
# The watchlist composition is private. It lives OUTSIDE Git in
# data_private\universe.csv (columns: id,ticker,sector,currency) and is the
# only source of names for this export - nothing about the book is committed.
$UniverseCsv = Join-Path $ProjectRoot "data_private\universe.csv"
if (-not (Test-Path $UniverseCsv)) {
    throw "data_private\universe.csv not found. Create it (columns: id,ticker,sector,currency) - the watchlist composition is never committed."
}
$Universe = @(Import-Csv $UniverseCsv | ForEach-Object {
    @{id=$_.id; ticker=$_.ticker; sector=$_.sector; currency=$_.currency}
})
Write-Host "Universe: $($Universe.Count) names (data_private\universe.csv)"

$Periods = @(0..($QuarterCount - 1) | ForEach-Object { if ($_ -eq 0) { "IQ_FQ" } else { "IQ_FQ-$_" } })

$MonthEnds = @(0..($ValuationMonths - 1) | ForEach-Object {
    (Get-Date -Day 1).AddMonths(-$_).AddDays(-1).ToString("MM/dd/yyyy")
})

# --- Helpers --------------------------------------------------------------------

function Get-OrCreateSheet($Name) {
    foreach ($Sheet in $Workbook.Worksheets) {
        if ($Sheet.Name -eq $Name) {
            $Sheet.Cells.Clear() | Out-Null
            return $Sheet
        }
    }
    $NewSheet = $Workbook.Worksheets.Add()
    $NewSheet.Name = $Name
    return $NewSheet
}

function Set-Headers($Sheet, [string[]]$Headers) {
    for ($Index = 0; $Index -lt $Headers.Count; $Index++) {
        $Sheet.Cells.Item(1, $Index + 1).Value2 = $Headers[$Index]
    }
}

function Invoke-CapIQRefreshAllSheets() {
    # Expand the "Refresh Data" split button and invoke "All Sheets" so the
    # whole workbook refreshes regardless of the add-in's scope setting.
    # (The main button fires "Refresh Selected Cells", which silently does
    # nothing useful when the selection has moved — the root cause of the
    # frozen pending counters in earlier runs.)
    $Process = Get-Process EXCEL | Select-Object -First 1
    $Root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $NameProperty = [System.Windows.Automation.AutomationElement]::NameProperty
    $TabCondition = New-Object System.Windows.Automation.PropertyCondition($NameProperty, "S&P Cap IQ Pro")
    $Tab = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $TabCondition)
    if ($null -ne $Tab) {
        try {
            $Tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() | Out-Null
        } catch {}
    }
    Start-Sleep -Milliseconds 600

    # Find the Refresh Data control and expand its dropdown.
    $Refresh = $null
    foreach ($Element in $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
        $ct = $Element.Current.ControlType.ProgrammaticName
        if ($Element.Current.Name -eq "Refresh Data" -and ($ct -eq "ControlType.SplitButton" -or $ct -eq "ControlType.Button" -or $ct -eq "ControlType.MenuItem")) {
            $Refresh = $Element
            if ($ct -eq "ControlType.SplitButton") { break }
        }
    }
    if ($null -eq $Refresh) { throw "Could not find the Capital IQ Refresh Data control." }

    $expanded = $false
    try {
        $Refresh.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() | Out-Null
        $expanded = $true
    } catch {}
    if (-not $expanded) {
        # Fall back: invoke opens the dropdown on some ribbon builds.
        try { $Refresh.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null } catch {}
    }
    Start-Sleep -Milliseconds 800

    $AllSheets = $null
    $AllSheetsCondition = New-Object System.Windows.Automation.PropertyCondition($NameProperty, "All Sheets")
    $AllSheets = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $AllSheetsCondition)
    if ($null -eq $AllSheets) {
        throw "Could not find the 'All Sheets' refresh option. Set Refresh Scope to 'Entire Workbook' in S&P Cap IQ Pro Settings and rerun."
    }
    $AllSheets.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() | Out-Null
}

function Wait-Pending($Sheet, [int]$TimeoutSeconds) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 5
        $Pending = 0
        foreach ($Cell in $Sheet.UsedRange.Cells) {
            if ([string]$Cell.Text -eq "#PEND") {
                $Pending++
            }
        }
        Write-Host "$($Sheet.Name) pending=$Pending"
    } while ($Pending -gt 0 -and (Get-Date) -lt $Deadline)
    return $Pending
}

function Get-HeaderMap($Sheet) {
    $Map = @{}
    for ($Column = 1; $Column -le $Sheet.UsedRange.Columns.Count; $Column++) {
        $Name = [string]$Sheet.Cells.Item(1, $Column).Text
        if ($Name) {
            $Map[$Name] = $Column
        }
    }
    return $Map
}

function Get-CellText($Sheet, $Row, $Map, $Name) {
    if (-not $Map.ContainsKey($Name)) {
        return $null
    }
    return [string]$Sheet.Cells.Item($Row, $Map[$Name]).Text
}

function To-Double($Value) {
    if ($null -eq $Value) { return $null }
    $Text = ([string]$Value).Trim()
    if ($Text -eq "" -or $Text -like "#*" -or $Text -like "(*Invalid*") { return $null }
    $Number = 0.0
    if ([double]::TryParse($Text, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::InvariantCulture, [ref]$Number)) {
        return $Number
    }
    if ([double]::TryParse($Text, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::CurrentCulture, [ref]$Number)) {
        return $Number
    }
    return $null
}

function ExcelSerialToDateString($Value) {
    $Serial = To-Double $Value
    if ($null -eq $Serial) { return $null }
    return ([datetime]"1899-12-30").AddDays([int][Math]::Round($Serial)).ToString("yyyy-MM-dd")
}

function TextToDateString($Value) {
    $FromSerial = ExcelSerialToDateString $Value
    if ($null -ne $FromSerial) { return $FromSerial }
    $Text = ([string]$Value).Trim()
    $Parsed = [datetime]::MinValue
    if ([datetime]::TryParse($Text, [ref]$Parsed)) {
        return $Parsed.ToString("yyyy-MM-dd")
    }
    return $null
}

# --- Sheet 1: companies ----------------------------------------------------------

$CompaniesSheet = Get-OrCreateSheet "companies_formula"
Set-Headers $CompaniesSheet @("company_id", "ticker", "company_name", "sector_capiq", "sector", "exchange", "currency", "source")
$Row = 2
foreach ($Company in $Universe) {
    $CompaniesSheet.Cells.Item($Row, 1).Value2 = $Company.id
    $CompaniesSheet.Cells.Item($Row, 2).Value2 = $Company.ticker
    $CompaniesSheet.Cells.Item($Row, 3).Formula = "=CIQ(""$($Company.id)"",""IQ_COMPANY_NAME"")"
    $CompaniesSheet.Cells.Item($Row, 4).Formula = "=CIQ(""$($Company.id)"",""IQ_INDUSTRY"")"
    $CompaniesSheet.Cells.Item($Row, 5).Value2 = $Company.sector
    $CompaniesSheet.Cells.Item($Row, 6).Formula = "=CIQ(""$($Company.id)"",""IQ_EXCHANGE"")"
    $CompaniesSheet.Cells.Item($Row, 7).Value2 = $Company.currency
    $CompaniesSheet.Cells.Item($Row, 8).Value2 = "Capital IQ Pro Excel Add-In"
    $Row++
}
$CompaniesSheet.Columns.AutoFit() | Out-Null

# --- Sheet 2: quarterly financials (20 quarters, deep-dive fields) -----------------

$FinancialsSheet = Get-OrCreateSheet "financials_formula"
Set-Headers $FinancialsSheet @(
    "company_id", "period_code", "period", "revenue", "gross_profit", "ebitda", "ebit",
    "net_income", "cfo", "capex_raw", "cash", "total_debt", "net_debt",
    "current_assets", "current_liabilities", "interest_expense_raw",
    "d_and_a", "sbc", "dividends_paid_raw", "buybacks_raw", "shares_diluted",
    "total_assets", "total_equity", "goodwill", "ar", "inventory", "ap",
    "minority_interest", "preferred_equity", "lease_liabilities",
    "pension_liabilities", "cash_st_invest", "tangible_common_equity"
)
$Fields = @(
    "IQ_PERIODDATE", "IQ_TOTAL_REV", "IQ_GP", "IQ_EBITDA", "IQ_EBIT", "IQ_NET_INC",
    "IQ_CASH_OPER", "IQ_CAPEX", "IQ_CASH_EQUIV", "IQ_TOTAL_DEBT", "IQ_NET_DEBT",
    "IQ_TOTAL_CURRENT_ASSETS", "IQ_TOTAL_CURRENT_LIAB", "IQ_INTEREST_EXP",
    "IQ_DA", "IQ_STOCK_BASED_COMP", "IQ_COMMON_DIV_CF", "IQ_COMMON_REP",
    "IQ_DILUT_WEIGHT", "IQ_TOTAL_ASSETS", "IQ_TOTAL_EQUITY", "IQ_GW",
    "IQ_AR", "IQ_INVENTORY", "IQ_AP",
    # EV-bridge / TEV components (invalid mnemonics degrade to null by design).
    "IQ_MINORITY_INTEREST", "IQ_PREF_EQUITY", "IQ_CAPITAL_LEASES",
    "IQ_PENSION", "IQ_CASH_ST_INVEST", "IQ_TBV"
)
$Row = 2
foreach ($Company in $Universe) {
    foreach ($Period in $Periods) {
        $FinancialsSheet.Cells.Item($Row, 1).Value2 = $Company.id
        $FinancialsSheet.Cells.Item($Row, 2).Value2 = $Period
        for ($Index = 0; $Index -lt $Fields.Count; $Index++) {
            $FinancialsSheet.Cells.Item($Row, $Index + 3).Formula = "=CIQ(""$($Company.id)"",""$($Fields[$Index])"",""$Period"")"
        }
        $Row++
    }
}
$FinancialsSheet.Columns.AutoFit() | Out-Null

# --- Sheet 3: current market snapshot ----------------------------------------------

$MarketSheet = Get-OrCreateSheet "market_formula"
Set-Headers $MarketSheet @("company_id", "share_price", "shares_outstanding", "market_cap", "enterprise_value")
# TEV must be pulled with an explicit as-of date: bare IQ_ENTERPRISE_VALUE
# returns a stale (period) print that can sit months behind the live price
# and market cap, which poisoned the EV-bridge audit for fast movers.
$TevAsOf = (Get-Date).ToString("MM/dd/yyyy")
$Row = 2
foreach ($Company in $Universe) {
    $MarketSheet.Cells.Item($Row, 1).Value2 = $Company.id
    $MarketSheet.Cells.Item($Row, 2).Formula = "=CIQ(""$($Company.id)"",""IQ_CLOSEPRICE"")"
    $MarketSheet.Cells.Item($Row, 3).Formula = "=CIQ(""$($Company.id)"",""IQ_SHARESOUTSTANDING"")"
    $MarketSheet.Cells.Item($Row, 4).Formula = "=CIQ(""$($Company.id)"",""IQ_MARKETCAP"")"
    $MarketSheet.Cells.Item($Row, 5).Formula = "=CIQ(""$($Company.id)"",""IQ_TEV"",""$TevAsOf"")"
    $Row++
}
$MarketSheet.Columns.AutoFit() | Out-Null

# --- Sheet 4: monthly valuation history --------------------------------------------

$ValuationSheet = Get-OrCreateSheet "valuation_formula"
Set-Headers $ValuationSheet @(
    "company_id", "date", "share_price", "market_cap", "enterprise_value",
    "ev_to_ebitda_ltm", "ev_to_revenue_ltm", "pe_ltm"
)
$Row = 2
foreach ($Company in $Universe) {
    foreach ($MonthEnd in $MonthEnds) {
        $ValuationSheet.Cells.Item($Row, 1).Value2 = $Company.id
        $ValuationSheet.Cells.Item($Row, 2).Value2 = $MonthEnd
        $ValuationSheet.Cells.Item($Row, 3).Formula = "=CIQ(""$($Company.id)"",""IQ_CLOSEPRICE"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 4).Formula = "=CIQ(""$($Company.id)"",""IQ_MARKETCAP"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 5).Formula = "=CIQ(""$($Company.id)"",""IQ_TEV"",""$MonthEnd"")"
        # Multiples need the period ("IQ_LTM") in the 3rd slot and the as-of
        # date in the 4th; a date in the period slot returns Invalid Time Period.
        $ValuationSheet.Cells.Item($Row, 6).Formula = "=CIQ(""$($Company.id)"",""IQ_TEV_EBITDA"",""IQ_LTM"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 7).Formula = "=CIQ(""$($Company.id)"",""IQ_TEV_TOTAL_REV"",""IQ_LTM"",""$MonthEnd"")"
        $ValuationSheet.Cells.Item($Row, 8).Formula = "=CIQ(""$($Company.id)"",""IQ_PE_EXCL"",""IQ_LTM"",""$MonthEnd"")"
        $Row++
    }
}

# --- Sheet 5: consensus estimates ---------------------------------------------------

$Date30 = (Get-Date).AddDays(-30).ToString("MM/dd/yyyy")
$Date90 = (Get-Date).AddDays(-90).ToString("MM/dd/yyyy")

$EstimatesSheet = Get-OrCreateSheet "estimates_formula"
Set-Headers $EstimatesSheet @(
    "company_id", "revenue_consensus", "ebitda_consensus", "eps_consensus",
    "revenue_est_ntm", "ebitda_est_ntm", "eps_est_ntm", "num_analysts",
    "revenue_est_ntm_30d_ago", "eps_est_ntm_30d_ago",
    "revenue_est_ntm_90d_ago", "eps_est_ntm_90d_ago", "next_earnings_date"
)
$Row = 2
foreach ($Company in $Universe) {
    $Id = $Company.id
    $EstimatesSheet.Cells.Item($Row, 1).Value2 = $Id
    $EstimatesSheet.Cells.Item($Row, 2).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_FQ"")"
    $EstimatesSheet.Cells.Item($Row, 3).Formula = "=CIQ(""$Id"",""IQ_EBITDA_EST"",""IQ_FQ"")"
    $EstimatesSheet.Cells.Item($Row, 4).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_FQ"")"
    $EstimatesSheet.Cells.Item($Row, 5).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item($Row, 6).Formula = "=CIQ(""$Id"",""IQ_EBITDA_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item($Row, 7).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item($Row, 8).Formula = "=CIQ(""$Id"",""IQ_REVENUE_NUM_EST"",""IQ_NTM"")"
    $EstimatesSheet.Cells.Item($Row, 9).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_NTM"",""$Date30"")"
    $EstimatesSheet.Cells.Item($Row, 10).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_NTM"",""$Date30"")"
    $EstimatesSheet.Cells.Item($Row, 11).Formula = "=CIQ(""$Id"",""IQ_REVENUE_EST"",""IQ_NTM"",""$Date90"")"
    $EstimatesSheet.Cells.Item($Row, 12).Formula = "=CIQ(""$Id"",""IQ_EPS_EST"",""IQ_NTM"",""$Date90"")"
    $EstimatesSheet.Cells.Item($Row, 13).Formula = "=CIQ(""$Id"",""IQ_NEXT_EARNINGS_DATE"")"
    $Row++
}
$EstimatesSheet.Columns.AutoFit() | Out-Null

$Workbook.SaveAs($WorkbookPath) | Out-Null
Write-Host "Workbook formula universe created: companies=$($Universe.Count) financial_rows=$($Universe.Count * $Periods.Count) valuation_rows=$($Universe.Count * $MonthEnds.Count)"

# --- Refresh (single workbook-wide pass) ------------------------------------------------

Invoke-CapIQRefreshAllSheets
$PendingCompanies = Wait-Pending $CompaniesSheet 600
$PendingFinancials = Wait-Pending $FinancialsSheet 1800
$PendingMarket = Wait-Pending $MarketSheet 360
$PendingValuation = Wait-Pending $ValuationSheet 1800
$PendingEstimates = Wait-Pending $EstimatesSheet 600
$Workbook.Save() | Out-Null
Write-Host "Final pending: companies=$PendingCompanies financials=$PendingFinancials market=$PendingMarket valuation=$PendingValuation estimates=$PendingEstimates"

# --- Scrape: companies ----------------------------------------------------------------

$CompaniesMap = Get-HeaderMap $CompaniesSheet
$Companies = @()
for ($Row = 2; $Row -le $CompaniesSheet.UsedRange.Rows.Count; $Row++) {
    $Id = Get-CellText $CompaniesSheet $Row $CompaniesMap "company_id"
    $Name = Get-CellText $CompaniesSheet $Row $CompaniesMap "company_name"
    if (-not $Id -or -not $Name -or $Name -like "(*Invalid*" -or $Name -like "#*") { continue }
    $Companies += [PSCustomObject]@{
        company_id = $Id
        ticker = Get-CellText $CompaniesSheet $Row $CompaniesMap "ticker"
        company_name = $Name
        sector = Get-CellText $CompaniesSheet $Row $CompaniesMap "sector"
        exchange = Get-CellText $CompaniesSheet $Row $CompaniesMap "exchange"
        currency = Get-CellText $CompaniesSheet $Row $CompaniesMap "currency"
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Companies | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "companies.csv")

# --- Scrape: financials ----------------------------------------------------------------

$FinancialsMap = Get-HeaderMap $FinancialsSheet
$Financials = @()
for ($Row = 2; $Row -le $FinancialsSheet.UsedRange.Rows.Count; $Row++) {
    $Id = Get-CellText $FinancialsSheet $Row $FinancialsMap "company_id"
    if (-not $Id) { continue }
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
        company_id = $Id
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
        minority_interest = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "minority_interest")
        preferred_equity = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "preferred_equity")
        lease_liabilities = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "lease_liabilities")
        pension_liabilities = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "pension_liabilities")
        cash_st_invest = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "cash_st_invest")
        tangible_common_equity = To-Double (Get-CellText $FinancialsSheet $Row $FinancialsMap "tangible_common_equity")
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Financials | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "financials_quarterly.csv")

$LatestPeriod = @{}
$Financials | Group-Object company_id | ForEach-Object {
    $LatestPeriod[$_.Name] = ($_.Group | Sort-Object period -Descending | Select-Object -First 1).period
}

# --- Scrape: market snapshot -------------------------------------------------------------

$MarketMap = Get-HeaderMap $MarketSheet
$Market = @()
for ($Row = 2; $Row -le $MarketSheet.UsedRange.Rows.Count; $Row++) {
    $Id = Get-CellText $MarketSheet $Row $MarketMap "company_id"
    if (-not $Id -or -not $LatestPeriod.ContainsKey($Id)) { continue }
    $SharesRaw = To-Double (Get-CellText $MarketSheet $Row $MarketMap "shares_outstanding")
    $Market += [PSCustomObject]@{
        company_id = $Id
        period = $LatestPeriod[$Id]
        share_price = To-Double (Get-CellText $MarketSheet $Row $MarketMap "share_price")
        shares_outstanding = if ($null -ne $SharesRaw) { [Math]::Round($SharesRaw * 1000000, 0) } else { $null }
        market_cap = To-Double (Get-CellText $MarketSheet $Row $MarketMap "market_cap")
        enterprise_value = To-Double (Get-CellText $MarketSheet $Row $MarketMap "enterprise_value")
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Market | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "market_data.csv")

# --- Scrape: valuation history ------------------------------------------------------------

$ValuationMap = Get-HeaderMap $ValuationSheet
$Valuation = @()
for ($Row = 2; $Row -le $ValuationSheet.UsedRange.Rows.Count; $Row++) {
    $Id = Get-CellText $ValuationSheet $Row $ValuationMap "company_id"
    if (-not $Id) { continue }
    $DateText = TextToDateString (Get-CellText $ValuationSheet $Row $ValuationMap "date")
    if (-not $DateText) { continue }
    $Price = To-Double (Get-CellText $ValuationSheet $Row $ValuationMap "share_price")
    if ($null -eq $Price) { continue }
    $Valuation += [PSCustomObject]@{
        company_id = $Id
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

# --- Scrape: estimates ---------------------------------------------------------------------

$EstimatesMap = Get-HeaderMap $EstimatesSheet
$Estimates = @()
for ($Row = 2; $Row -le $EstimatesSheet.UsedRange.Rows.Count; $Row++) {
    $Id = Get-CellText $EstimatesSheet $Row $EstimatesMap "company_id"
    if (-not $Id -or -not $LatestPeriod.ContainsKey($Id)) { continue }
    $Estimates += [PSCustomObject]@{
        company_id = $Id
        period = $LatestPeriod[$Id]
        revenue_consensus = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "revenue_consensus")
        ebitda_consensus = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "ebitda_consensus")
        eps_consensus = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "eps_consensus")
        guidance_low = $null
        guidance_high = $null
        revenue_est_ntm = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "revenue_est_ntm")
        ebitda_est_ntm = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "ebitda_est_ntm")
        eps_est_ntm = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "eps_est_ntm")
        num_analysts = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "num_analysts")
        revenue_est_ntm_30d_ago = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "revenue_est_ntm_30d_ago")
        eps_est_ntm_30d_ago = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "eps_est_ntm_30d_ago")
        revenue_est_ntm_90d_ago = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "revenue_est_ntm_90d_ago")
        eps_est_ntm_90d_ago = To-Double (Get-CellText $EstimatesSheet $Row $EstimatesMap "eps_est_ntm_90d_ago")
        next_earnings_date = TextToDateString (Get-CellText $EstimatesSheet $Row $EstimatesMap "next_earnings_date")
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Estimates | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "estimates.csv")

# --- Source log + refresh log -----------------------------------------------------------------

$RetrievedAt = (Get-Date).ToString("yyyy-MM-dd")
$SourceLog = @(
    [PSCustomObject]@{ table_name = "companies"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Investment watchlist universe (composition private, data_private/universe.csv); financial data from Capital IQ." },
    [PSCustomObject]@{ table_name = "financials_quarterly"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Latest $QuarterCount fiscal quarters in local currency millions, incl. D&A, SBC, capital returns, balance-sheet detail." },
    [PSCustomObject]@{ table_name = "market_data"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Current market snapshot linked to each company's latest reported quarter." },
    [PSCustomObject]@{ table_name = "valuation_history"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Monthly valuation series, trailing $ValuationMonths months (price, market cap, TEV, LTM multiples)." },
    [PSCustomObject]@{ table_name = "estimates"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Consensus for current quarter and NTM, with 30d/90d-ago as-of snapshots for revision momentum." }
)
$SourceLog | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "source_log.csv")

$RefreshLogPath = Join-Path $OutDir "refresh_log.csv"
$RefreshEntry = [PSCustomObject]@{
    refreshed_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    duration_minutes = [Math]::Round(((Get-Date) - $RunStart).TotalMinutes, 1)
    companies = $Companies.Count
    financial_rows = $Financials.Count
    market_rows = $Market.Count
    valuation_rows = $Valuation.Count
    estimate_rows = $Estimates.Count
    pending_financials = $PendingFinancials
    pending_valuation = $PendingValuation
    pending_estimates = $PendingEstimates
}
if (Test-Path $RefreshLogPath) {
    $RefreshEntry | Export-Csv -NoTypeInformation -Encoding UTF8 -Append -Path $RefreshLogPath
} else {
    $RefreshEntry | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $RefreshLogPath
}

Write-Host "Exported companies=$($Companies.Count) financials=$($Financials.Count) market=$($Market.Count) valuation=$($Valuation.Count) estimates=$($Estimates.Count)"
Write-Host "Refresh logged to $RefreshLogPath"
