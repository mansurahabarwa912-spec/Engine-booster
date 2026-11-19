
"""
Engine Booster v2 - USA - Scoring + DSCR + Loan + Lender Matching
"""
from pydantic import BaseModel
from typing import Optional, List, Dict
import uuid, math

COST_PER_KW = 1450.0
ITC_RATE = 0.30
CORP_TAX_RATE = 0.21
TARGET_OFFSET = 0.85
W_PER_SQFT = 15.0

class UnderwritingInput(BaseModel):
    property_address: str
    annual_kwh: float
    electricity_rate_kwh: float
    roof_area_sqft: float = 30000
    roof_type: str = "Flat"
    business_years: int = 5
    credit_score: int = 700
    pvwatts_per_kw: float = 1450
    annual_revenue: Optional[float] = 2400000
    annual_net_income: Optional[float] = None  # if provided, use it; else estimate 15% of revenue
    existing_annual_debt: Optional[float] = 0  # existing debt service
    down_payment_pct: Optional[float] = 0.10
    loan_term_years: Optional[int] = 10
    loan_rate: Optional[float] = 0.075  # 7.5% default commercial solar loan

# --- LENDER DATABASE - USA 2026 ---
# Add / edit lenders here. This is your matching engine.
LENDERS = [
    {"name": "EnFin / Sunrun Commercial", "min_credit": 680, "min_years": 2, "min_dscr": 1.20, "max_kw": 1000, "rate": 0.069, "term_years": 12, "max_loan": 5000000, "products": ["Loan", "PPA"], "notes": "Fast approval, best for 680+ credit"},
    {"name": "Mosaic Commercial", "min_credit": 660, "min_years": 2, "min_dscr": 1.15, "max_kw": 500, "rate": 0.074, "term_years": 10, "max_loan": 2000000, "products": ["Loan"], "notes": "Good for mid-size rooftop"},
    {"name": "GoodLeap Commercial", "min_credit": 640, "min_years": 1, "min_dscr": 1.05, "max_kw": 750, "rate": 0.082, "term_years": 10, "max_loan": 3000000, "products": ["Loan", "Lease"], "notes": "Flexible - accepts lower credit / younger business"},
    {"name": "PACE / C-PACE Provider (e.g. PACE Equity)", "min_credit": 600, "min_years": 1, "min_dscr": 1.0, "max_kw": 2000, "rate": 0.068, "term_years": 20, "max_loan": 10000000, "products": ["C-PACE"], "notes": "Property-assessed, no PG, long term, great for RED/AMBER deals"},
    {"name": "SBA 504 / SBA 7(a) Lender", "min_credit": 680, "min_years": 3, "min_dscr": 1.25, "max_kw": 1000, "rate": 0.065, "term_years": 20, "max_loan": 5500000, "products": ["SBA Loan"], "notes": "Lowest rate, slowest - 45-60 days"},
    {"name": "Credit Human / Local Credit Union", "min_credit": 660, "min_years": 3, "min_dscr": 1.20, "max_kw": 300, "rate": 0.071, "term_years": 10, "max_loan": 1000000, "products": ["Loan"], "notes": "Best for <300kW local deals"},
]

def pmt(rate_annual: float, n_years: int, principal: float) -> float:
    """Monthly payment"""
    if principal <= 0: return 0.0
    r = rate_annual / 12
    n = n_years * 12
    if r == 0: return principal / n
    return principal * r / (1 - (1 + r) ** -n)

def match_lenders(system_kw: float, credit: int, years: int, dscr: float, loan_amount: float) -> List[Dict]:
    matched = []
    for L in LENDERS:
        reasons = []
        eligible = True
        if credit < L["min_credit"]: eligible=False; reasons.append(f"Credit {credit} < {L['min_credit']}")
        if years < L["min_years"]: eligible=False; reasons.append(f"Years {years} < {L['min_years']}")
        if dscr < L["min_dscr"]: eligible=False; reasons.append(f"DSCR {dscr:.2f} < {L['min_dscr']}")
        if system_kw > L["max_kw"]: eligible=False; reasons.append(f"System {system_kw}kW > max {L['max_kw']}kW")
        if loan_amount > L["max_loan"]: eligible=False; reasons.append(f"Loan ${loan_amount:,.0f} > max ${L['max_loan']:,.0f}")
        monthly = pmt(L["rate"], L["term_years"], loan_amount)
        matched.append({
            "lender": L["name"],
            "eligible": eligible,
            "products": L["products"],
            "rate": L["rate"],
            "term_years": L["term_years"],
            "monthly_payment": round(monthly, 2),
            "annual_debt_service": round(monthly*12, 2),
            "notes": L["notes"],
            "blockers": reasons if not eligible else [],
            "score": 100 if eligible else max(0, 100 - len(reasons)*25)
        })
    # Sort: eligible first, then lowest rate
    matched.sort(key=lambda x: (not x["eligible"], x["rate"]))
    return matched

def calculate_underwriting(inp: UnderwritingInput) -> dict:
    roof_factor = {"Flat": 0.98, "Metal": 1.01, "Pitched": 1.0, "Ground": 1.03, "Carport": 0.97}.get(inp.roof_type, 0.98)
    pvwatts_adj = round(inp.pvwatts_per_kw * roof_factor, 1)
    by_usage = (inp.annual_kwh * TARGET_OFFSET) / pvwatts_adj if pvwatts_adj else 0
    by_roof = (inp.roof_area_sqft * W_PER_SQFT) / 1000.0
    system_kw = round(min(by_usage, by_roof, 1000), 1)
    production = round(system_kw * pvwatts_adj, 0)
    project_cost = round(system_kw * COST_PER_KW, 2)
    tax_credit = round(project_cost * ITC_RATE, 2)
    net_cost = round(project_cost - tax_credit, 2)
    depreciation_benefit = round(project_cost * 0.85, 2)
    depreciation_tax_savings = round(depreciation_benefit * CORP_TAX_RATE, 2)
    year1_savings = round(min(production, inp.annual_kwh) * inp.electricity_rate_kwh, 2)
    simple_payback = round(project_cost / year1_savings, 2) if year1_savings else 0
    year1_net = round(year1_savings + tax_credit + depreciation_tax_savings, 2)
    incentive_payback = round((project_cost - tax_credit - depreciation_tax_savings) / year1_savings, 2) if year1_savings else 0

    # --- DSCR + LOAN ---
    # NOI proxy: if net income given use it, else 15% of revenue + solar savings (savings increase NOI)
    base_noi = inp.annual_net_income if inp.annual_net_income else (inp.annual_revenue or 0) * 0.15
    noi_with_solar = base_noi + year1_savings
    down = round(project_cost * (inp.down_payment_pct or 0.10), 2)
    loan_amount = round(project_cost - down, 2)
    monthly_payment = round(pmt(inp.loan_rate or 0.075, inp.loan_term_years or 10, loan_amount), 2)
    annual_debt = round(monthly_payment * 12, 2)
    total_debt_service = annual_debt + (inp.existing_annual_debt or 0)
    dscr = round(noi_with_solar / total_debt_service, 2) if total_debt_service else 99.99
    # DSCR without solar for comparison
    dscr_no_solar = round(base_noi / total_debt_service, 2) if total_debt_service else 99.99
    max_loan_at_125_dscr = round((noi_with_solar / 1.25 - (inp.existing_annual_debt or 0)) / 12, 2)  # max monthly
    # Max financeable: loan that keeps DSCR >=1.25 at chosen rate/term
    # Solve: max annual debt = NOI/1.25 - existing, convert to principal via PMT inverse
    max_annual_debt = noi_with_solar / 1.25 - (inp.existing_annual_debt or 0)
    r = (inp.loan_rate or 0.075)/12; n = (inp.loan_term_years or 10)*12
    max_loan = round((max_annual_debt/12) * (1 - (1+r)**-n) / r, 2) if r and max_annual_debt>0 else 0

    # Flag now includes DSCR
    if simple_payback < 6 and inp.business_years >= 3 and inp.credit_score >= 680 and dscr >= 1.25:
        flag = "GREEN"; flag_reason = f"DSCR {dscr} >= 1.25, payback {simple_payback}yr, credit {inp.credit_score}"
        summary = f"GREEN - {system_kw}kW at {inp.property_address} producing {production:,.0f} kWh/yr. Savings ${year1_savings:,.0f}/yr, DSCR {dscr}, payback {simple_payback}yr ({incentive_payback}yr after incentives). Ready to advance."
    elif simple_payback <= 8 and inp.business_years >= 2 and inp.credit_score >= 640 and dscr >= 1.0:
        flag = "AMBER"; flag_reason = f"DSCR {dscr} 1.0-1.24 or payback {simple_payback}yr - conditional"
        summary = f"AMBER - {system_kw}kW at {inp.property_address}. Savings ${year1_savings:,.0f}/yr, DSCR {dscr}, payback {simple_payback}yr. Conditional: may need larger down payment, PG, or C-PACE."
    else:
        flag = "RED"; flag_reason = f"DSCR {dscr} < 1.0 or payback {simple_payback}yr or credit {inp.credit_score}"
        summary = f"RED - {system_kw}kW at {inp.property_address}. Savings ${year1_savings:,.0f}/yr, DSCR {dscr}, payback {simple_payback}yr. Does not meet preliminary criteria - consider C-PACE, larger down payment, or PPA (no debt)."

    lenders = match_lenders(system_kw, inp.credit_score, inp.business_years, dscr, loan_amount)
    best = next((l for l in lenders if l["eligible"]), None)

    deal_id = f"EB-{uuid.uuid4().hex[:6].upper()}"
    return {
        "deal_id": deal_id,
        "property_address": inp.property_address,
        "ai_estimated_annual_solar_production_kwh": production,
        "ai_pvwatts_production_per_kw": pvwatts_adj,
        "ai_preliminary_system_size_kw": system_kw,
        "ai_electricity_rate_kwh": round(inp.electricity_rate_kwh, 4),
        "ai_estimated_year_1_savings_": year1_savings,
        "ai_simple_payback_period_years": simple_payback,
        "ai_estimated_project_cost_": project_cost,
        "ai_preliminary_tax_credit_rate_": ITC_RATE,
        "ai_estimated_tax_credit": tax_credit,
        "ai_project_cost": project_cost,
        "ai_net_project_cost": net_cost,
        "ai_estimated_depreciation_benefit": depreciation_benefit,
        "ai_estimated_depreciation_tax_savings": depreciation_tax_savings,
        "ai_year_1_net_economic_benefit": year1_net,
        "ai_incentive_adjusted_payback": incentive_payback,
        "ai_underwriting_review_flag": flag,
        "ai_underwriting_summary": summary,
        # --- NEW v2 fields ---
        "ai_annual_revenue": inp.annual_revenue,
        "ai_noi_with_solar": round(noi_with_solar, 2),
        "ai_down_payment": down,
        "ai_loan_amount": loan_amount,
        "ai_loan_rate": inp.loan_rate,
        "ai_loan_term_years": inp.loan_term_years,
        "ai_monthly_loan_payment": monthly_payment,
        "ai_annual_debt_service": annual_debt,
        "ai_dscr": dscr,
        "ai_dscr_without_solar": dscr_no_solar,
        "ai_max_financeable_loan": max_loan,
        "ai_recommended_lender": best["lender"] if best else "C-PACE / PPA - No debt lender matched",
        "ai_recommended_product": best["products"][0] if best else "C-PACE or PPA",
        "ai_lender_matches": lenders,
        "ai_flag_reason": flag_reason,
        "ai_underwriting_report_url": f"https://enginebooster.app/report/{deal_id}",
    }
