"""
Engine Booster v3 - USA
Microsoft Edge (Chromium) Optimized - NOT Internet Explorer
IE is deprecated / unsupported. Edge = Chromium. All frontend uses modern Chromium APIs only.
Flow: Upload Bill -> Extract -> PVWatts -> Calculate -> DSCR/Lender -> Push to GHL
"""
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.underwriting.scoring import calculate_underwriting, UnderwritingInput
from app.underwriting.pvwatts import get_pvwatts_per_kw, geocode_address
from app.underwriting.bill_parser import extract_bill_data
from app.underwriting.lenders import calculate_lending
from app.integrations.gohighlevel import push_to_ghl, GHL_FIELDS

app = FastAPI(title="Engine Booster v3 - USA - Edge Optimized", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ManualInput(BaseModel):
    property_address: str
    annual_kwh: float
    electricity_rate_kwh: Optional[float] = None
    monthly_bill: Optional[float] = None
    roof_area_sqft: Optional[float] = 30000
    roof_type: Optional[str] = "Flat"
    business_years: Optional[int] = 5
    credit_score: Optional[int] = 700
    annual_revenue: Optional[float] = 2400000
    annual_net_income: Optional[float] = None
    annual_noi: Optional[float] = 420000
    existing_annual_debt: Optional[float] = 0
    down_pct: Optional[float] = 0.20
    down_payment_pct: Optional[float] = None
    loan_rate: Optional[float] = 0.075
    loan_term_years: Optional[int] = 10
    contact_id: Optional[str] = None
    opportunity_id: Optional[str] = None

@app.get("/health")
def health():
    return {"status": "ok", "market": "USA", "version": "3.0.0", "browser": "Microsoft Edge (Chromium) - NOT Internet Explorer", "ie_supported": False}

@app.get("/edge")
def edge_info():
    return {
        "browser": "Microsoft Edge",
        "engine": "Chromium (Blink + V8) - same as Chrome",
        "ie_supported": False,
        "ie_note": "Internet Explorer 11 was retired June 15, 2022 by Microsoft. Do NOT test in IE. Use Edge.",
        "open_in_edge": "microsoft-edge:https://enginebooster.app",
        "install_as_app": "Edge > ... > Apps > Install this site as an app",
        "pwa_manifest": "/edge/manifest.json"
    }

@app.post("/api/v1/underwrite")
async def underwrite_manual(payload: ManualInput):
    lat, lon = await geocode_address(payload.property_address)
    pvwatts = await get_pvwatts_per_kw(lat, lon)
    down = payload.down_payment_pct if payload.down_payment_pct is not None else payload.down_pct
    inp = UnderwritingInput(
        property_address=payload.property_address,
        annual_kwh=payload.annual_kwh,
        electricity_rate_kwh=payload.electricity_rate_kwh or (payload.monthly_bill*12/payload.annual_kwh if payload.monthly_bill else 0.17),
        roof_area_sqft=payload.roof_area_sqft or 30000,
        roof_type=payload.roof_type or "Flat",
        business_years=payload.business_years or 5,
        credit_score=payload.credit_score or 700,
        pvwatts_per_kw=pvwatts,
        annual_revenue=payload.annual_revenue,
        annual_net_income=payload.annual_net_income,
        existing_annual_debt=payload.existing_annual_debt or 0,
        down_payment_pct=down or 0.20,
        loan_term_years=payload.loan_term_years or 10,
        loan_rate=payload.loan_rate or 0.075,
    )
    report = calculate_underwriting(inp)
    # v3: DSCR + Lender uses NOI field (fallback to annual_noi)
    noi = payload.annual_noi or (payload.annual_net_income or (payload.annual_revenue or 0)*0.15)
    lending = calculate_lending(report["ai_net_project_cost"], noi, down or 0.20, payload.loan_rate or 0.075, payload.loan_term_years or 10, payload.credit_score or 700, payload.business_years or 5, report["ai_preliminary_system_size_kw"])
    report.update(lending)
    # Also add v2 DSCR fields from scoring for consistency
    if payload.contact_id:
        await push_to_ghl(payload.contact_id, report, opportunity_id=payload.opportunity_id)
    return report

@app.post("/api/v1/underwrite-bill")
async def underwrite_bill(file: UploadFile = File(...), contact_id: str = Form(None), opportunity_id: str = Form(None), roof_area_sqft: float = Form(30000), roof_type: str = Form("Flat"), business_years: int = Form(5), credit_score: int = Form(700), annual_noi: float = Form(420000), down_pct: float = Form(0.20), loan_rate: float = Form(0.075), loan_term_years: int = Form(10)):
    if not file.filename.lower().endswith((".pdf",".png",".jpg",".jpeg",".webp")):
        raise HTTPException(400, "Upload PDF or image of utility bill")
    content = await file.read()
    bill = extract_bill_data(content, file.filename)
    if not bill.get("property_address") or not bill.get("annual_kwh"):
        raise HTTPException(422, f"Could not extract address/kWh. Got: {bill}")
    lat, lon = await geocode_address(bill["property_address"])
    pvwatts = await get_pvwatts_per_kw(lat, lon)
    inp = UnderwritingInput(property_address=bill["property_address"], annual_kwh=bill["annual_kwh"], electricity_rate_kwh=bill["electricity_rate_kwh"], roof_area_sqft=roof_area_sqft, roof_type=roof_type, business_years=business_years, credit_score=credit_score, pvwatts_per_kw=pvwatts, down_payment_pct=down_pct, loan_term_years=loan_term_years, loan_rate=loan_rate)
    report = calculate_underwriting(inp)
    lending = calculate_lending(report["ai_net_project_cost"], annual_noi, down_pct, loan_rate, loan_term_years, credit_score, business_years, report["ai_preliminary_system_size_kw"])
    report.update(lending)
    report["bill_extraction"] = bill
    if contact_id:
        report["ghl_push"] = await push_to_ghl(contact_id, report, opportunity_id=opportunity_id)
    return report

@app.get("/api/v1/ghl-fields")
def ghl_fields(): return GHL_FIELDS


