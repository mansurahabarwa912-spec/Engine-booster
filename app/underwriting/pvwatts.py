import os, httpx
from geopy.geocoders import Nominatim
NREL_KEY=os.getenv("NREL_API_KEY","")
async def geocode_address(address: str):
    try:
        geo=Nominatim(user_agent="engine-booster-v3-edge")
        loc=geo.geocode(address)
        if loc: return loc.latitude, loc.longitude
    except: pass
    return 33.4484,-112.0740
async def get_pvwatts_per_kw(lat: float, lon: float) -> float:
    if not NREL_KEY: return 1450.0
    url="https://developer.nrel.gov/api/pvwatts/v8.json"
    params={"api_key":NREL_KEY,"lat":lat,"lon":lon,"system_capacity":1,"azimuth":180,"tilt":20,"array_type":1,"module_type":1,"losses":14.08,"dataset":"nsrdb","timeframe":"hourly"}
    async with httpx.AsyncClient(timeout=20) as client:
        r=await client.get(url,params=params); r.raise_for_status(); data=r.json()
        ac=data.get("outputs",{}).get("ac_annual")
        return float(ac) if ac else 1450.0
