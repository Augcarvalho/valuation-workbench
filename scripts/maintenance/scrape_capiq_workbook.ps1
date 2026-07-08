# Scrape-only harvester for the CapIQ watchlist workbook.
#
# Reads the already-refreshed formula sheets from the OPEN Excel workbook and
# exports them to private CSVs. Never writes formulas, never clears sheets,
# never clicks Refresh — safe to run any time the workbook holds resolved
# values (e.g. after a manual refresh).
#
# Outputs (all inside data_private/, gitignored):
#   companies.csv, financials_quarterly.csv, market_data.csv,
#   valuation_history.csv, estimates.csv, source_log.csv, refresh_log.csv

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $ProjectRoot "data_private\capiq_exports"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$RunStart = Get-Date

$Excel = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
$Workbook = $Excel.ActiveWorkbook
if ($null -eq $Workbook) { throw "No active workbook in Excel." }
Write-Host "Scraping workbook: $($Workbook.Name)"

function Get-SheetArray($Name) {
    foreach ($Sheet in $Workbook.Worksheets) {
        if ($Sheet.Name -eq $Name) {
            $Used = $Sheet.UsedRange
            return @{ values = $Used.Value2; rows = $Used.Rows.Count; cols = $Used.Columns.Count }
        }
    }
    return $null
}

function Build-HeaderMap($Data) {
    $Map = @{}
    for ($c = 1; $c -le $Data.cols; $c++) {
        $h = $Data.values[1, $c]
        if ($h -is [string] -and $h) { $Map[$h] = $c }
    }
    return $Map
}

function Get-Val($Data, $Row, $Map, $Name) {
    if (-not $Map.ContainsKey($Name)) { return $null }
    return $Data.values[$Row, $Map[$Name]]
}

function As-Double($Value) {
    if ($Value -is [double]) { return $Value }
    if ($Value -is [string]) {
        $t = $Value.Trim()
        if ($t -eq "" -or $t -like "#*" -or $t -like "(*Invalid*" -or $t -eq "NM" -or $t -eq "NA") { return $null }
        $n = 0.0
        if ([double]::TryParse($t, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::InvariantCulture, [ref]$n)) { return $n }
        if ([double]::TryParse($t, [Globalization.NumberStyles]::Any, [Globalization.CultureInfo]::CurrentCulture, [ref]$n)) { return $n }
    }
    return $null   # error codes (Int32), nulls, anything else
}

function As-AbsDouble($Value) {
    $d = As-Double $Value
    if ($null -ne $d) { return [Math]::Abs($d) }
    return $null
}

function As-DateString($Value) {
    if ($Value -is [double]) { return [datetime]::FromOADate($Value).ToString("yyyy-MM-dd") }
    if ($Value -is [string]) {
        $p = [datetime]::MinValue
        if ([datetime]::TryParse($Value.Trim(), [ref]$p)) { return $p.ToString("yyyy-MM-dd") }
    }
    return $null
}

function As-Text($Value) {
    if ($Value -is [string]) {
        $t = $Value.Trim()
        if ($t -like "#*" -or $t -like "(*Invalid*") { return $null }
        return $t
    }
    if ($Value -is [double]) { return [string]$Value }
    return $null
}

# --- companies -----------------------------------------------------------------

$D = Get-SheetArray "companies_formula"
if ($null -eq $D) { throw "companies_formula sheet not found." }
$M = Build-HeaderMap $D
$Companies = @()
for ($r = 2; $r -le $D.rows; $r++) {
    $Id = As-Text (Get-Val $D $r $M "company_id")
    $Name = As-Text (Get-Val $D $r $M "company_name")
    if (-not $Id -or -not $Name) { continue }
    $Companies += [PSCustomObject]@{
        company_id = $Id
        ticker = As-Text (Get-Val $D $r $M "ticker")
        company_name = $Name
        sector = As-Text (Get-Val $D $r $M "sector")
        exchange = As-Text (Get-Val $D $r $M "exchange")
        currency = As-Text (Get-Val $D $r $M "currency")
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Companies | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "companies.csv")
Write-Host "companies: $($Companies.Count)"

# --- financials -----------------------------------------------------------------

$D = Get-SheetArray "financials_formula"
if ($null -eq $D) { throw "financials_formula sheet not found." }
$M = Build-HeaderMap $D
$Financials = @()
for ($r = 2; $r -le $D.rows; $r++) {
    $Id = As-Text (Get-Val $D $r $M "company_id")
    if (-not $Id) { continue }
    $Period = As-DateString (Get-Val $D $r $M "period")
    if (-not $Period) { continue }
    $Cfo = As-Double (Get-Val $D $r $M "cfo")
    $Capex = As-AbsDouble (Get-Val $D $r $M "capex_raw")
    $CA = As-Double (Get-Val $D $r $M "current_assets")
    $CL = As-Double (Get-Val $D $r $M "current_liabilities")
    $Financials += [PSCustomObject]@{
        company_id = $Id
        period = $Period
        revenue = As-Double (Get-Val $D $r $M "revenue")
        gross_profit = As-Double (Get-Val $D $r $M "gross_profit")
        ebitda = As-Double (Get-Val $D $r $M "ebitda")
        ebit = As-Double (Get-Val $D $r $M "ebit")
        net_income = As-Double (Get-Val $D $r $M "net_income")
        cfo = $Cfo
        capex = $Capex
        fcf = if ($null -ne $Cfo -and $null -ne $Capex) { $Cfo - $Capex } else { $null }
        cash = As-Double (Get-Val $D $r $M "cash")
        total_debt = As-Double (Get-Val $D $r $M "total_debt")
        net_debt = As-Double (Get-Val $D $r $M "net_debt")
        working_capital = if ($null -ne $CA -and $null -ne $CL) { $CA - $CL } else { $null }
        interest_expense = As-AbsDouble (Get-Val $D $r $M "interest_expense_raw")
        d_and_a = As-Double (Get-Val $D $r $M "d_and_a")
        sbc = As-Double (Get-Val $D $r $M "sbc")
        dividends_paid = As-AbsDouble (Get-Val $D $r $M "dividends_paid_raw")
        buybacks = As-AbsDouble (Get-Val $D $r $M "buybacks_raw")
        shares_diluted = As-Double (Get-Val $D $r $M "shares_diluted")
        total_assets = As-Double (Get-Val $D $r $M "total_assets")
        total_equity = As-Double (Get-Val $D $r $M "total_equity")
        goodwill = As-Double (Get-Val $D $r $M "goodwill")
        ar = As-Double (Get-Val $D $r $M "ar")
        inventory = As-Double (Get-Val $D $r $M "inventory")
        ap = As-Double (Get-Val $D $r $M "ap")
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Financials | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "financials_quarterly.csv")
Write-Host "financial rows: $($Financials.Count)"

$LatestPeriod = @{}
$Financials | Group-Object company_id | ForEach-Object {
    $LatestPeriod[$_.Name] = ($_.Group | Sort-Object period -Descending | Select-Object -First 1).period
}

# --- market snapshot ---------------------------------------------------------------

$D = Get-SheetArray "market_formula"
if ($null -eq $D) { throw "market_formula sheet not found." }
$M = Build-HeaderMap $D
$Market = @()
for ($r = 2; $r -le $D.rows; $r++) {
    $Id = As-Text (Get-Val $D $r $M "company_id")
    if (-not $Id -or -not $LatestPeriod.ContainsKey($Id)) { continue }
    $Shares = As-Double (Get-Val $D $r $M "shares_outstanding")
    $Market += [PSCustomObject]@{
        company_id = $Id
        period = $LatestPeriod[$Id]
        share_price = As-Double (Get-Val $D $r $M "share_price")
        shares_outstanding = if ($null -ne $Shares) { [Math]::Round($Shares * 1000000, 0) } else { $null }
        market_cap = As-Double (Get-Val $D $r $M "market_cap")
        enterprise_value = As-Double (Get-Val $D $r $M "enterprise_value")
        source = "Capital IQ Pro Excel Add-In"
    }
}
$Market | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "market_data.csv")
Write-Host "market rows: $($Market.Count)"

# --- valuation history ----------------------------------------------------------------

$D = Get-SheetArray "valuation_formula"
$Valuation = @()
if ($null -ne $D) {
    $M = Build-HeaderMap $D
    for ($r = 2; $r -le $D.rows; $r++) {
        $Id = As-Text (Get-Val $D $r $M "company_id")
        if (-not $Id) { continue }
        $DateText = As-DateString (Get-Val $D $r $M "date")
        if (-not $DateText) { continue }
        $Price = As-Double (Get-Val $D $r $M "share_price")
        $Cap = As-Double (Get-Val $D $r $M "market_cap")
        if ($null -eq $Price -and $null -eq $Cap) { continue }
        $Valuation += [PSCustomObject]@{
            company_id = $Id
            date = $DateText
            share_price = $Price
            market_cap = $Cap
            enterprise_value = As-Double (Get-Val $D $r $M "enterprise_value")
            ev_to_ebitda_ltm = As-Double (Get-Val $D $r $M "ev_to_ebitda_ltm")
            ev_to_revenue_ltm = As-Double (Get-Val $D $r $M "ev_to_revenue_ltm")
            pe_ltm = As-Double (Get-Val $D $r $M "pe_ltm")
            source = "Capital IQ Pro Excel Add-In"
        }
    }
}
$Valuation | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "valuation_history.csv")
Write-Host "valuation rows: $($Valuation.Count)"

# --- estimates ---------------------------------------------------------------------------

$D = Get-SheetArray "estimates_formula"
$Estimates = @()
if ($null -ne $D) {
    $M = Build-HeaderMap $D
    for ($r = 2; $r -le $D.rows; $r++) {
        $Id = As-Text (Get-Val $D $r $M "company_id")
        if (-not $Id -or -not $LatestPeriod.ContainsKey($Id)) { continue }
        $Estimates += [PSCustomObject]@{
            company_id = $Id
            period = $LatestPeriod[$Id]
            revenue_consensus = As-Double (Get-Val $D $r $M "revenue_consensus")
            ebitda_consensus = As-Double (Get-Val $D $r $M "ebitda_consensus")
            eps_consensus = As-Double (Get-Val $D $r $M "eps_consensus")
            guidance_low = $null
            guidance_high = $null
            revenue_est_ntm = As-Double (Get-Val $D $r $M "revenue_est_ntm")
            ebitda_est_ntm = As-Double (Get-Val $D $r $M "ebitda_est_ntm")
            eps_est_ntm = As-Double (Get-Val $D $r $M "eps_est_ntm")
            num_analysts = As-Double (Get-Val $D $r $M "num_analysts")
            revenue_est_ntm_30d_ago = As-Double (Get-Val $D $r $M "revenue_est_ntm_30d_ago")
            eps_est_ntm_30d_ago = As-Double (Get-Val $D $r $M "eps_est_ntm_30d_ago")
            revenue_est_ntm_90d_ago = As-Double (Get-Val $D $r $M "revenue_est_ntm_90d_ago")
            eps_est_ntm_90d_ago = As-Double (Get-Val $D $r $M "eps_est_ntm_90d_ago")
            next_earnings_date = As-DateString (Get-Val $D $r $M "next_earnings_date")
            source = "Capital IQ Pro Excel Add-In"
        }
    }
}
$Estimates | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "estimates.csv")
Write-Host "estimate rows: $($Estimates.Count)"

# --- logs ---------------------------------------------------------------------------------

$RetrievedAt = (Get-Date).ToString("yyyy-MM-dd")
$SourceLog = @(
    [PSCustomObject]@{ table_name = "companies"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Investment watchlist universe (composition private); financial data from Capital IQ." },
    [PSCustomObject]@{ table_name = "financials_quarterly"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "20 fiscal quarters in local currency millions, incl. D&A, SBC, capital returns, balance-sheet detail." },
    [PSCustomObject]@{ table_name = "market_data"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Current market snapshot linked to each company's latest reported quarter." },
    [PSCustomObject]@{ table_name = "valuation_history"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Monthly valuation series (price, market cap, TEV, LTM multiples)." },
    [PSCustomObject]@{ table_name = "estimates"; source_name = "Capital IQ Pro Excel Add-In"; source_url = "local private export"; retrieved_at = $RetrievedAt; notes = "Consensus for current quarter and NTM, with 30d/90d-ago snapshots for revision momentum." }
)
$SourceLog | Export-Csv -NoTypeInformation -Encoding UTF8 -Path (Join-Path $OutDir "source_log.csv")

$RefreshLogPath = Join-Path $OutDir "refresh_log.csv"
$Entry = [PSCustomObject]@{
    refreshed_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    duration_minutes = [Math]::Round(((Get-Date) - $RunStart).TotalMinutes, 1)
    companies = $Companies.Count
    financial_rows = $Financials.Count
    market_rows = $Market.Count
    valuation_rows = $Valuation.Count
    estimate_rows = $Estimates.Count
    pending_financials = 0
    pending_valuation = 0
    pending_estimates = 0
}
if (Test-Path $RefreshLogPath) { $Entry | Export-Csv -NoTypeInformation -Encoding UTF8 -Append -Path $RefreshLogPath }
else { $Entry | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $RefreshLogPath }

Write-Host "DONE: companies=$($Companies.Count) financials=$($Financials.Count) market=$($Market.Count) valuation=$($Valuation.Count) estimates=$($Estimates.Count)"
