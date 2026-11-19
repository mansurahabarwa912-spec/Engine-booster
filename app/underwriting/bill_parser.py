import re, io
try:
 import pdfplumber
except: pdfplumber=None
from PIL import Image
try:
 import pytesseract
except: pytesseract=None
def _text(content,filename):
    if filename.lower().endswith(".pdf") and pdfplumber:
        with pdfplumber.open(io.BytesIO(content)) as pdf: return "\n".join([(p.extract_text() or "") for p in pdf.pages])
    if pytesseract:
        return pytesseract.image_to_string(Image.open(io.BytesIO(content)))
    return ""
def extract_bill_data(content,filename):
    text=_text(content,filename)
    m=re.search(r"(?:Service Address|Service Location|Service For|Property Address)[:\s]*\n?(.+)",text,re.I)
    address=m.group(1).strip() if m else ""
    if not address:
        mm=re.search(r"\d+\s+[A-Za-z0-9 ]+\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Way|Dr|Drive|Ln|Lane)[^,\n]*,\s*[A-Z]{2}\s*\d{5}",text)
        address=mm.group(0) if mm else ""
    kwh=re.findall(r"(\d[\d,]*\.?\d*)\s*kWh",text,re.I)
    annual=0
    if kwh:
        vals=[float(x.replace(",","")) for x in kwh]; annual=max(vals)*12 if max(vals)<20000 else max(vals)
    tot=re.findall(r"Total\s+(?:Due|Amount|Charges)[^\d$]*\$?([\d,]+\.\d{2})",text,re.I)
    monthly=float(tot[0].replace(",","")) if tot else 0
    rate=round(monthly*12/annual,4) if annual and monthly else 0.17
    return {"property_address":address,"annual_kwh":annual,"monthly_bill":monthly,"electricity_rate_kwh":rate,"raw_text_preview":text[:2000]}
