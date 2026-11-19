
import os, httpx
GHL_API_KEY=os.getenv("GHL_API_KEY",""); GHL_LOCATION_ID=os.getenv("GHL_LOCATION_ID",""); GHL_BASE="https://services.leadconnectorhq.com"
GHL_FIELDS={k:k for k in ["property_address","ai_estimated_annual_solar_production_kwh","ai_pvwatts_production_per_kw","ai_preliminary_system_size_kw","ai_electricity_rate_kwh","ai_estimated_year_1_savings_","ai_simple_payback_period_years","ai_estimated_project_cost_","ai_preliminary_tax_credit_rate_","ai_estimated_tax_credit","ai_project_cost","ai_net_project_cost","ai_estimated_depreciation_benefit","ai_estimated_depreciation_tax_savings","ai_year_1_net_economic_benefit","ai_incentive_adjusted_payback","ai_underwriting_review_flag","ai_underwriting_summary","ai_underwriting_report_url","ai_annual_revenue","ai_noi_with_solar","ai_down_payment","ai_loan_amount","ai_loan_rate","ai_loan_term_years","ai_monthly_loan_payment","ai_annual_debt_service","ai_dscr","ai_dscr_without_solar","ai_max_financeable_loan","ai_recommended_lender","ai_recommended_product","ai_flag_reason","ai_dscr_verdict","ai_best_lender","ai_lender_match"]}
async def push_to_ghl(contact_id: str, report: dict, opportunity_id: str=None):
    if not GHL_API_KEY or not contact_id: return {"skipped":True}
    headers={"Authorization":f"Bearer {GHL_API_KEY}","Version":os.getenv("GHL_API_VERSION","2021-07-28"),"Content-Type":"application/json"}
    custom=[{"id":k,"field_value":str(report[k])} for k in GHL_FIELDS if k in report]
    # lender matches is a list - store as summary string for GHL
    if "ai_lender_matches" in report:
        custom.append({"id":"ai_lender_matches_summary","field_value":", ".join([f"{m['lender']}:{m['status']}" for m in report["ai_lender_matches"]])})
    payload={"customFields":custom,"locationId":GHL_LOCATION_ID}
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.put(f"{GHL_BASE}/contacts/{contact_id}",json=payload,headers=headers)
        return {"status":r.status_code,"body":r.text[:500],"opportunity_stage_target":{"GREEN":"Approved - Preliminary","AMBER":"Conditional Review","RED":"Needs Review"}.get(report.get("ai_underwriting_review_flag"))}
