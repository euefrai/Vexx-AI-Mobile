"""Real live-data adapters, research-only fixtures, disposable DB guard inherited."""
import json
import os
from pathlib import Path
import time
import research_fixture_agent_v592  # validates temp database + explicit fixture opt-in
import live_data
import pc_agent

TRACE=Path(os.environ['VEXX_LIVE_TRACE'])

def record(item):
    with TRACE.open('a',encoding='utf-8') as out:out.write(json.dumps(item,ensure_ascii=False)+'\n')

_geo=live_data.geocode
_get=live_data.get_json

def geocode(city):
    start=time.monotonic()
    result=_geo(city)
    record(dict(kind='geocode',query=city,result=result,latency_ms=round((time.monotonic()-start)*1000)))
    return result

def get(base,params):
    start=time.monotonic()
    try:
        result=_get(base,params)
        record(dict(kind='api',host=base,params=params,current=result.get('current'),daily=result.get('daily'),units=result.get('current_units'),timezone=result.get('timezone'),latency_ms=round((time.monotonic()-start)*1000)))
        return result
    except Exception as exc:
        record(dict(kind='api_error',host=base,error=type(exc).__name__,latency_ms=round((time.monotonic()-start)*1000)))
        raise

live_data.geocode=geocode
live_data.get_json=get
if __name__=='__main__':pc_agent.run()
