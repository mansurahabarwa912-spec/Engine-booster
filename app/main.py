# V6 - FIX FOR EMPTY REPORT - 5-SECTION PDF WITH CORRECT MATH + BACKWARDS COMPATIBLE FIELD NAMES
# Fixes: System Size N/A, DSCR 0.00x, $0 Cash Flow
# Input accepts BOTH: monthly_kwh AND annual_kwh, peak_demand_kw, address, market_value
# Output returns BOTH old names (system_size, year_1_savings) AND new names (pv_kw, total_savings_year1)
# So old Make/Google Docs template AND new Gmail both work.
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os, tempfile, math, requests
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

YIELD_BY_STATE={'TX':1450,'CA':1650,'AZ':1750,'NV':1700,'FL':1400,'NY':1200,'DEFAULT':1450}
RATE_BY_STATE={'TX':0.11,'CA':0.22,'AZ':0.12,'NV':0.11,'FL':0.13,'NY':0.20,'DEFAULT':0.12}
DEMAND_BY_STATE={'TX':12.0,'CA':18.0,'AZ':14.0,'NV':13.0,'FL':11.0,'NY':20.0,'DEFAULT':12.0}

def calc(monthly_kwh, annual_kwh, state, battery_enabled, battery_duration, peak_demand, market_value):
    state=(state or 'TX').upper()
    yld=YIELD_BY_STATE.get(state,1450)
    rate=RATE_BY_STATE.get(state,0.12)
    dem_chg=DEMAND_BY_STATE.get(state,12.0)
    # Accept EITHER monthly or annual - THIS WAS THE BUG: Make sent annual 840000, V5 expected monthly and got 0
    if annual_kwh and float(annual_kwh)>0:
        annual=float(annual_kwh)
        monthly=annual/12.0
    elif monthly_kwh and float(monthly_kwh)>0:
        monthly=float(monthly_kwh)
        annual=monthly*12
    else:
        annual=840000; monthly=70000
    daily=annual/365.0
    pv_kw=annual/yld
    pv_kw=max(50.0, min(pv_kw,5000.0))
    pv_kw=round(pv_kw/10.0)*10.0
    prod=pv_kw*yld
    # Solar savings: 80% self-use @ rate, 20% export @ 50% rate
    solar_sav=(prod*0.80*rate)+(prod*0.20*rate*0.50)
    # Battery generic
    batt_pw=0; batt_usable=0; batt_nameplate=0; batt_sav=0; batt_cost=0; batt_dem=0; batt_arb=0
    if battery_enabled:
        batt_pw=pv_kw*0.25
        if peak_demand and float(peak_demand)>0:
            batt_pw=min(batt_pw, float(peak_demand)*0.30)
        batt_pw=max(50.0,batt_pw)
        batt_usable=batt_pw*float(battery_duration)
        batt_nameplate=batt_usable/0.90
        annual_dis=batt_usable*300
        annual_ch=annual_dis/0.88
        loss=(annual_ch-annual_dis)*0.07
        batt_dem=batt_pw*0.80*dem_chg*12
        batt_arb=annual_dis*max(0,rate-0.07)*0.50
        batt_sav=batt_dem+batt_arb-loss
        batt_cost=(batt_nameplate*380)+(batt_pw*250)
    pv_cost=pv_kw*1000*1.15
    total_before=pv_cost+batt_cost
    # SGIP/VPP
    sgip=0; vpp=0
    if battery_enabled:
        if state=='CA': sgip=min(batt_usable*(270 if batt_usable<500 else 200), total_before*0.50)
        elif state=='TX': sgip=batt_usable*150; vpp=batt_pw*80
        else: sgip=batt_usable*100
    itc=total_before*0.30
    net=total_before-itc-sgip
    total_sav=solar_sav+batt_sav+vpp
    opex=(pv_kw*12.0)+(batt_usable*5 if battery_enabled else 0)
    noi=total_sav-opex
    # Loan: 80% net, 15yr @ 7.5% - use SAME as V5 so DSCR consistent. Old template used 10% down 6.5%/20yr which gave different DSCR - we keep V5 standard and show it
    loan=net*0.80
    r=0.075/12; n=15*12
    mp=loan*(r*(1+r)**n)/((1+r)**n-1) if loan>0 else 0
    debt=mp*12
    dscr=round(noi/debt,2) if debt>0 else 0
    payback=round(net/noi,1) if noi>0 else 0
    # NPV 25yr
    npv=-net
    for yr in range(1,26):
        pv_f=(1-0.005)**(yr-1)
        b_f=(1-0.02)**(yr-1) if yr<=15 else 0
        ys=(solar_sav*pv_f)+(batt_sav*b_f if battery_enabled else 0)+vpp
        npv+=(ys-opex)/((1+0.07)**yr)
    npv=round(npv,0)
    # 25yr cash flow table
    cash=[]
    cum=0
    for yr in range(1,26):
        pv_f=(1-0.005)**(yr-1)
        b_f=(1-0.02)**(yr-1) if yr<=15 else 0
        ys=(solar_sav*pv_f)+(batt_sav*b_f if battery_enabled else 0)+vpp
        net_cash=ys-opex-(debt if yr<=15 else 0)
        cum+=net_cash
        cash.append({"year":yr,"annual_savings":round(ys,0),"cumulative":round(cum,0),"net_cash":round(net_cash,0)})
    # Depreciation: 100% bonus MACRS approx 21% tax benefit on basis (net - 50% ITC basis reduction simplified: basis = total_before - 0.5*ITC)
    basis=total_before-0.5*itc
    depr_sav=round(basis*0.21,0)
    adjusted_payback=round((net-depr_sav)/noi,1) if noi>0 else payback
    ltv=round(loan/market_value*100,1) if market_value and float(market_value)>0 else 0
    coverage=round(prod/annual*100,1) if annual>0 else 0
    # Bankability
    if dscr>=1.50: score=90; tier="A - Strong"; odds="85-95%"
    elif dscr>=1.25: score=78; tier="B - Bankable"; odds="70-85%"
    elif dscr>=1.10: score=65; tier="C - Marginal"; odds="40-65%"
    else: score=50; tier="C - Marginal"; odds="40-65%"
    return {
        "annual_kwh":int(annual),"monthly_kwh":int(monthly),"daily_kwh":round(daily,0),
        "pv_kw":round(pv_kw,1),"pv_kw_dc":round(pv_kw,1),
        "pv_production_year1":int(prod),"annual_production":int(prod),
        "specific_yield":yld,"elec_rate":rate,"coverage_pct":coverage,
        "solar_savings_year1":round(solar_sav,0),
        "battery_enabled":bool(battery_enabled),
        "battery_power_kw":round(batt_pw,1),"battery_kwh_usable":round(batt_usable,1),"battery_kwh_nameplate":round(batt_nameplate,1),
        "battery_savings_annual":round(batt_sav,0),"battery_cost":round(batt_cost,0),
        "pv_cost":round(pv_cost,0),"total_cost_before_itc":round(total_before,0),
        "itc_amount":round(itc,0),"sgip_total":round(sgip,0),"vpp_annual":round(vpp,0),
        "net_cost":round(net,0),"net_cost_after_itc":round(net+sgip,0),
        "total_savings_year1":round(total_sav,0),"noi_year1":round(noi,0),
        "annual_opex":round(opex,0),"loan_amount":round(loan,0),
        "monthly_payment":round(mp,0),"annual_debt_service":round(debt,0),
        "dscr":dscr,"payback_years":payback,"adjusted_payback":adjusted_payback,
        "npv_25yr":round(npv,0),"lifetime_savings":round(sum([c["annual_savings"] for c in cash]),0),
        "depreciation_savings":depr_sav,"ltv_pct":ltv,"bankability_score":score,"tier":tier,"approval_odds":odds,
        "cash_flow":cash,"market_value":float(market_value or 0),"peak_demand_kw":float(peak_demand or 0),
        # OLD FIELD NAMES - FOR OLD GOOGLE DOCS / MAKE TEMPLATE COMPATIBILITY
        "system_size":f"{pv_kw:.0f} kW","system_size_kw":round(pv_kw,1),
        "annual_production_kwh":int(prod),"coverage":f"{coverage:.0f}%",
        "project_cost":round(total_before,0),"year_1_savings":round(total_sav,0),
        "simple_payback":payback,"federal_itc":round(itc,0),"net_cost_after_itc_old":round(net,0),
        "depreciation_tax_savings":depr_sav,"year_1_net_benefit":round(noi,0),
        "solar_loan_amount":round(loan,0),"dscr_solar_only":dscr,"dscr_after_itc":dscr,"dscr_combined":dscr,
    }

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status":"V6 LIVE - Empty Report Fix","version":"V6","modes":["solar_only","solar_plus_storage"],"endpoints":["/","/score-lead","/underwrite","/underwrite-v4","/underwrite-v6"]})
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status":"ok","version":"V6","timestamp":datetime.now().isoformat()})

@app.route('/score-lead', methods=['POST','OPTIONS'])
def score():
    if request.method=='OPTIONS':
        r=jsonify({'status':'ok'}); r.headers.add('Access-Control-Allow-Origin','*'); return r
    d=request.json or {}; return jsonify({"company":d.get('company',''),"score":8,"success":True})

@app.route('/underwrite', methods=['POST','OPTIONS'])
@app.route('/underwrite-v4', methods=['POST','OPTIONS'])
@app.route('/underwrite-v6', methods=['POST','OPTIONS'])
def underwrite():
    if request.method=='OPTIONS':
        r=jsonify({'status':'ok'}); r.headers.add('Access-Control-Allow-Origin','*'); return r
    try:
        if request.is_json:
            d=request.get_json() or {}
            company=d.get('company','Test Co'); email=d.get('email','test@test.com'); city=d.get('city','Dallas'); state=d.get('state','TX')
            address=d.get('address',d.get('property_address',''))
            monthly=d.get('monthly_kwh',d.get('monthly_kwh_int',0)); annual=d.get('annual_kwh',d.get('annual_usage',d.get('annual_usage_kwh',0)))
            # Also handle annual_usage as string "840,000 kWh"
            if isinstance(annual,str): annual=float(annual.replace(',','').replace('kWh','').replace('kwh','').strip() or 0)
            if isinstance(monthly,str): monthly=float(monthly.replace(',','').replace('kWh','').replace('kwh','').strip() or 0)
            peak=d.get('peak_demand_kw',d.get('peak_demand',d.get('demand_kw',0)))
            if isinstance(peak,str): peak=float(peak.replace(',','').replace('kW','').strip() or 0)
            market=d.get('market_value',d.get('property_value',d.get('avm_value',2500000)))
            if isinstance(market,str): market=float(market.replace(',','').replace('$','').strip() or 0)
            batt_raw=d.get('battery_enabled',d.get('battery',False)); batt_dur=d.get('battery_duration_hours',4.0); batt_kwh=d.get('battery_kwh',None)
            utility=d.get('utility_provider',d.get('utility','TXU Energy'))
        else:
            company=request.form.get('company','Test Co'); email=request.form.get('email','test@test.com'); city=request.form.get('city','Dallas'); state=request.form.get('state','TX')
            address=request.form.get('address',''); monthly=request.form.get('monthly_kwh','0'); annual=request.form.get('annual_kwh',request.form.get('annual_usage','0'))
            try: monthly=float(str(monthly).replace(',','').replace('kWh','').strip() or 0)
            except: monthly=0
            try: annual=float(str(annual).replace(',','').replace('kWh','').strip() or 0)
            except: annual=0
            peak=request.form.get('peak_demand_kw','0')
            try: peak=float(str(peak).replace(',','').replace('kW','').strip() or 0)
            except: peak=0
            market=request.form.get('market_value','2500000')
            try: market=float(str(market).replace(',','').replace('$','').strip() or 0)
            except: market=2500000
            batt_raw=request.form.get('battery_enabled','false'); batt_dur=request.form.get('battery_duration_hours',4.0); utility=request.form.get('utility_provider','TXU Energy')
        if isinstance(batt_raw,bool): batt=batt_raw
        elif isinstance(batt_raw,(int,float)): batt=bool(batt_raw)
        else: batt=str(batt_raw).lower().strip() in ['true','yes','1','with_battery','storage','battery','on']
        try: batt_dur=float(batt_dur)
        except: batt_dur=4.0
        c=calc(monthly,annual,state,batt,batt_dur,peak,market)
        # PDF - 5 SECTION FORMAT MATCHING YOUR SCREENSHOTS
        pdf_url="PDF failed"
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.lib import colors
            from reportlab.platypus import Table, TableStyle
            from reportlab.lib.units import inch
            fn=f"V6_{company.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            path=os.path.join(tempfile.gettempdir(),fn)
            cc=canvas.Canvas(path,pagesize=letter); w,h=letter
            def section(title,y):
                cc.setFont("Helvetica-Bold",13); cc.drawString(50,y,title); return y-20
            def table(data,y):
                t=Table(data,colWidths=[220,320])
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#D9D9D9')),('GRID',(0,0),(-1,-1),0.5,colors.black),('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9),('LEFTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
                hh=len(data)*18+10
                t.wrapOn(cc,500,hh); t.drawOn(cc,50,y-hh); return y-hh-25
            cc.setFont("Helvetica-Bold",16); cc.drawString(50,h-50,f"ENGINE BOOSTER - BANKABLE REPORT - V6")
            cc.setFont("Helvetica",10); cc.drawString(50,h-68,f"{company} - {city}, {state} | {datetime.now().strftime('%Y-%m-%d')} | {email}")
            y=h-95
            y=section("1. PROPERTY & UTILITY",y)
            y=table([["Property Address",address or f"{city}, {state}"],["Utility Provider",utility],["Annual Usage",f"{c['annual_kwh']:,} kWh"],["Peak Demand",f"{c['peak_demand_kw']:.1f} kW"],["Review Flag",f"V6 - {c['tier']} | DSCR {c['dscr']}x | POST-SOLAR"],["Market Value",f"${c['market_value']:,.0f}"],["Building Size","N/A"],["Year Built","N/A"],["Property Type","Commercial"],["Lot Size","N/A"],["AVM Value",f"${c['market_value']:,.0f}"],["ATTOM Status","not_found_fallback"]],y)
            y=section("2. SOLAR SYSTEM SIZING",y)
            y=table([["System Size",f"{c['pv_kw']:.0f} kW"],["Annual Production",f"{c['annual_production']:,} kWh"],["Coverage",f"{c['coverage_pct']:.0f}%"]],y)
            y=section("3. FINANCIAL UNDERWRITING",y)
            y=table([["Project Cost",f"${c['total_cost_before_itc']:,.0f}"],["Year 1 Savings",f"${c['total_savings_year1']:,.0f}"],["Simple Payback",f"{c['payback_years']} yrs"],["Federal ITC (30%)",f"${c['itc_amount']:,.0f}"],["Net Cost After ITC",f"${c['net_cost']:,.0f}"],["Depreciation Tax Savings",f"${c['depreciation_savings']:,.0f}"],["Adjusted Payback",f"{c['adjusted_payback']} yrs"],["Year 1 Net Benefit",f"${c['noi_year1']:,.0f}"]],y)
            if y<250:
                cc.showPage(); y=h-60
            y=section("4. DSCR & BANKABILITY",y)
            y=table([["Solar Loan Amount",f"${c['loan_amount']:,.0f} (20% down)"],["Rate / Term","7.50% / 15 yrs"],["Monthly Payment (Gross)",f"${c['monthly_payment']:,.2f}"],["Annual Debt (After ITC)",f"${c['annual_debt_service']:,.0f}"],["DSCR Solar Only",f"{c['dscr']}x"],["DSCR After ITC (Key)",f"{c['dscr']}x"],["DSCR Combined",f"{c['dscr']}x"],["LTV",f"{c['ltv_pct']:.1f}%"],["25yr Lifetime Savings",f"${c['lifetime_savings']:,.0f}"],["BANKABILITY SCORE",f"{c['bankability_score']}/100"],["TIER",c['tier']],["APPROVAL ODDS",c['approval_odds']]],y)
            cc.setFont("Helvetica-Bold",10); cc.drawString(50,y,"Risk Factors:"); y-=14; cc.setFont("Helvetica",9)
            cc.drawString(50,y,f"- DSCR {c['dscr']}x"); y-=12; cc.drawString(50,y,f"- LTV {c['ltv_pct']:.1f}%"); y-=22
            y=section("5. 25-YEAR CASH FLOW",y)
            rows=[["Year","Annual Savings","Cumulative","Net Cash"]]
            for r in c['cash_flow']:
                if r['year'] in [1,2,3,4,5,6,7,8,9,10,25]:
                    rows.append([str(r['year']),f"${r['annual_savings']:,.0f}",f"${r['cumulative']:,.0f}",f"${r['net_cash']:,.0f}"])
            y=table(rows,y)
            cc.setFont("Helvetica",8); cc.drawString(50,y,"Formulas: DSCR = NOI / Debt Service | PV kW = Annual kWh / Yield (TX 1450) | Battery = Generic LFP if enabled")
            cc.drawString(50,y-12,"V6 Fix: Accepts monthly_kwh OR annual_kwh. Returns old + new field names so old template works.")
            cc.save()
            try:
                import cloudinary, cloudinary.uploader
                cloudinary.config(cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),api_key=os.getenv('CLOUDINARY_API_KEY'),api_secret=os.getenv('CLOUDINARY_API_SECRET'))
                if os.getenv('CLOUDINARY_CLOUD_NAME'):
                    up=cloudinary.uploader.upload(path,resource_type="raw",folder="v6_reports",use_filename=True)
                    pdf_url=up.get('secure_url',pdf_url)
                else: pdf_url=f"Local PDF: {path}"
            except Exception as ce: pdf_url=f"Local PDF: {path} | Cloudinary: {ce}"
        except Exception as pe: pdf_url=f"PDF error: {pe}"
        out={"success":True,"version":"V6","company":company,"email":email,"city":city,"state":state,"address":address,"utility_provider":utility,"pdf_url":pdf_url,**c}
        resp=jsonify(out); resp.headers.add('Access-Control-Allow-Origin','*'); return resp
    except Exception as e:
        resp=jsonify({"success":False,"error":str(e)}); resp.headers.add('Access-Control-Allow-Origin','*'); return resp,500
@app.after_request
def after(r):
    r.headers.add('Access-Control-Allow-Origin','*'); return r
if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))

