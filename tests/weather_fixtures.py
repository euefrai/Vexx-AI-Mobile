"""Explicit Visual Crossing provider fixtures for existing rendering regressions."""
from datetime import datetime
from zoneinfo import ZoneInfo

def timeline(data,lat=-12.97,lon=-38.5):
    import live_data
    c=data['current'];d=data.get('daily',{})
    result=dict(queryCost=1,latitude=lat,longitude=lon,timezone=data['timezone'],unitGroup='metric',
        currentConditions=dict(datetimeEpoch=datetime.fromisoformat(c['time']).replace(tzinfo=ZoneInfo(data['timezone'])).timestamp(),
            temp=c['temperature_2m'],feelslike=c['apparent_temperature'],humidity=c['relative_humidity_2m'],
            windspeed=c['wind_speed_10m'],conditions=live_data.condition(c.get('weather_code')),source='fcst'),days=[])
    for i,date in enumerate(d.get('time',[])):
        result['days'].append(dict(datetime=date,tempmin=d['temperature_2m_min'][i],tempmax=d['temperature_2m_max'][i],
            precipprob=d['precipitation_probability_max'][i],conditions=live_data.condition(d['weather_code'][i]),source='fcst'))
    if data.get('current_units',{}).get('temperature_2m','°C')!='°C':result['unitGroup']='us'
    return result

def photon(rows):
    return {'features':[dict(type='Feature',properties=dict(name=r['name'],state=r.get('admin1',''),
        country=r.get('country',''),countrycode=r.get('country_code','BR')),
        geometry=dict(type='Point',coordinates=[r['longitude'],r['latitude']])) for r in rows]}
