
"""
Lender Matching + DSCR + Loan Payment - v3 USA - Edge/Chromium only
"""
LENDERS = [
    {"name": "GoodLeap Commercial", "min_dscr": 1.25, "max_loan": 1500000, "rate": 0.0695, "term_years": 15, "min_credit": 680, "min_years": 3},
    {"name": "EnerBank Solar Commercial", "min_dscr": 1.20, "max_loan": 2000000, "rate": 0.0725, "term_years": 10, "min_credit": 660, "min_years": 2},
    {"name": "Dividend Finance - Commercial", "min_dscr": 1.15, "max_loan": 5000000, "rate": 0.0775, "term_years": 12, "min_credit": 640, "min_years": 2},
    {"name": "Mosaic Commercial", "min_dscr": 1.30, "max_loan": 1000000, "rate": 0.0750, "term_years": 10, "min_credit": 700, "min_years": 3},
    {"name": "C-PACE Provider", "min_dscr": 1.00, "max_loan": 10000000, "rate": 0.068, "term_years": 20, "min_credit": 600, "min_years": 1},
]
def pmt(loan, annual_rate, term_years):
    r = annual_rate/12; n = term_years*12
    return loan/n if r==0 else loan*r/(1-(1+r)**-n)
def calculate_lending(net_project_cost, annual_noi, down_pct=0.20, rate=0.075, term_years=10, credit_score=700, business_years=5, system_kw=0):
    loan_amount = round(net_project_cost*(1-down_pct),2)
    monthly = round(pmt(loan_amount, rate, term_years),2)
    annual_debt = round(monthly*12,2)
    dscr = round(annual_noi/annual_debt,3) if annual_debt else 0
    verdict = "Bankable" if dscr>=1.25 else "Conditional - needs PG / reserves" if dscr>=1.0 else "Not bankable - DSCR < 1.0"
    matches=[]
    for l in LENDERS:
        lm = round(pmt(loan_amount, l["rate"], l["term_years"]),2); la = lm*12; ld = round(annual_noi/la,3) if la else 0
        reasons=[]
        reasons.append(f"DSCR {ld} >= {l['min_dscr']}" if ld>=l["min_dscr"] else f"DSCR {ld} < {l['min_dscr']} required")
        reasons.append(f"Loan ${loan_amount:,.0f} within ${l['max_loan']:,.0f}" if loan_amount<=l["max_loan"] else f"Loan exceeds ${l['max_loan']:,.0f}")
        reasons.append(f"Credit {credit_score} >= {l['min_credit']}" if credit_score>=l["min_credit"] else f"Credit {credit_score} < {l['min_credit']}")
        score = (40 if ld>=l["min_dscr"] else 0)+(25 if loan_amount<=l["max_loan"] else 0)+(20 if credit_score>=l["min_credit"] else 0)+(15 if business_years>=l["min_years"] else 0)
        status = "MATCHED" if score>=85 else "CONDITIONAL" if score>=60 else "NOT MATCHED"
        matches.append({"lender":l["name"],"rate":l["rate"],"term_years":l["term_years"],"monthly_payment":lm,"dscr_at_lender":ld,"match_score":score,"status":status,"why":" | ".join(reasons)})
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    best = matches[0] if matches else None
    return {"ai_loan_amount":loan_amount,"ai_monthly_payment":monthly,"ai_annual_debt_service":annual_debt,"ai_dscr":dscr,"ai_dscr_verdict":verdict,"ai_lender_matches":matches,"ai_best_lender":best["lender"] if best else None,"ai_lender_match":best["status"] if best else None,"ai_recommended_lender":best["lender"] if best else None}
