"""Shared evidence contracts and extraction for the existing retrieval engine.

No requests, inferred inventory, model code, or parallel engine. Structured data
is a source declaration, never independently verified availability.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import TypedDict
import query_intelligence as qi


class SourceContract(TypedDict):
    kind: str
    url: str
    eligible: bool
    verification: str
    reasons: list[str]
    data: dict


def text(value, limit=400):
    if isinstance(value, dict):
        value = value.get('name') or value.get('addressLocality') or ''
    return re.sub('<[^>]+>', '', str(value or ''))[:limit].strip()


def contains(value, content):
    return bool(re.search(r'(?<!\w)'+re.escape(qi.normalized(value))+r'(?!\w)', qi.normalized(content))) if value else False


def structured(page):
    import web_extract
    nodes=web_extract._ld_por_tipo(web_extract._ldjson_objs(page[:2_000_000]), {'event','musicevent','theaterevent','businessevent','flight','bustrip'}, teto=8)
    out=[]
    for n in nodes:
        kind=str(n.get('@type','')).lower()
        row={'kind':'event' if kind.endswith('event') else 'air_travel' if kind=='flight' else 'bus_travel'}
        for key in ('name','startDate','endDate','departureTime','arrivalTime','eventStatus'):
            if n.get(key): row[key]=text(n[key])
        for key in ('location','organizer','provider','airline','departureAirport','arrivalAirport','departureBusStop','arrivalBusStop'):
            if n.get(key): row[key]=text(n[key])
        offers=n.get('offers') or {}
        if isinstance(offers,list): offers=next((v for v in offers if isinstance(v,dict)),{})
        if isinstance(offers,dict):
            # Keep only finite declared amounts; assess() still requires exact trip match.
            try:
                amount=Decimal(str(offers.get('price','')))
                if amount.is_finite() and amount>0 and re.fullmatch('[A-Z]{3}',str(offers.get('priceCurrency',''))):
                    row.update(declared_price=str(amount),currency=offers['priceCurrency'])
            except InvalidOperation: pass
            for key in ('url','availability','validThrough'):
                if offers.get(key): row[key]=text(offers[key],500)
        if n.get('numAdults') and type(n['numAdults']) is int: row['adults']=n['numAdults']
        out.append(row)
    return out


def assess(request, source) -> SourceContract:
    domain=request['domain'];p=request.get('parameters') or {}
    body=text(source.get('titulo'),1000)+' '+str(source.get('trecho') or '')
    data={};reasons=[];state='UNVERIFIED';eligible=True
    if domain in ('news','events') and p.get('location'):
        if not contains(p['location'],body): reasons.append('ENTITY_MISMATCH')
        region = {'BA': 'Bahia', 'PE': 'Pernambuco', 'SP': 'São Paulo'}.get(str(p.get('region','')).upper(), p.get('region'))
        if region and not (contains(region,body) or contains(p['region'],body)): reasons.append('SOURCE_MISMATCH')
    if domain=='news':
        if p.get('topic'):
            import search_orchestrator
            terms=search_orchestrator._termos(p['topic'])
            if terms and not any(contains(term,body) for term in terms):
                reasons.append('TOPIC_MISMATCH')
        if source.get('tipo')=='enciclopedia' or re.search(r'\b(turismo|pontos turisticos|wikipedia)\b',qi.normalized(source.get('titulo',''))):
            reasons.append('INTENT_MISMATCH')
        published=source.get('publicado_em') or (source.get('meta') or {}).get('publicado_em')
        if p.get('start_date') or p.get('start_at'):
            import search_orchestrator
            dt=search_orchestrator._data_do_item(source)
            if not dt: reasons.append('INCOMPLETE_EVIDENCE')
            elif p.get('start_date') and not p.get('start_at'):
                from zoneinfo import ZoneInfo
                # Publication instants must be compared in the request's zone.
                # A source's date-only declaration is already a calendar date.
                day = (str(published).strip() if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(published).strip())
                       else dt.astimezone(ZoneInfo(request.get('timezone') or 'UTC')).date().isoformat())
                if not p['start_date']<=day<=p['end_date']: reasons.append('TEMPORAL_MISMATCH')
        if published: data['published_at']=str(published)[:48]
        if p.get('start_at'):
            if not published or len(str(published).strip()) <= 10:
                reasons.append('INCOMPLETE_EVIDENCE')
            elif dt and not datetime.fromisoformat(p['start_at']) <= dt <= datetime.fromisoformat(p['end_at']):
                reasons.append('TEMPORAL_MISMATCH')
        import search_orchestrator
        if source.get('pagina_de_indice') or search_orchestrator._pagina_de_indice(source):
            reasons.append('INDEX_PAGE')
        state='PUBLISHED_REPORT' if not reasons else 'UNVERIFIED'
    if domain=='events':
        event=next((r for r in source.get('structured',[]) if r.get('kind')=='event' and contains(p.get('location'),r.get('location','')+' '+r.get('name',''))),{})
        declared=event.get('startDate') or source.get('event_date') or source.get('data_evento')
        try:
            dt=date.fromisoformat(str(declared)[:10]).isoformat()
            if p.get('start_date') and not p['start_date']<=dt<=p['end_date']: reasons.append('TEMPORAL_MISMATCH')
            else: data={**event,'event_date':str(declared)[:48]}
        except (ValueError,TypeError): reasons.append('INCOMPLETE_EVIDENCE')
        state='DECLARED_EVENT' if data and not reasons else 'CONTEXT_ONLY'
    if domain in ('air_travel','bus_travel'):
        if p.get('origin') and p.get('destination'):
            if not all(contains(p[k],body) for k in ('origin','destination')): reasons.append('ENTITY_MISMATCH')
        mode=r'\b(onibus|rodoviari[ao]|bustrip)\b' if domain=='bus_travel' else r'\b(voos?|aereas?|aeroportos?|flight)\b'
        if not re.search(mode,qi.normalized(body)): reasons.append('INTENT_MISMATCH')
        structured_trip=any(r.get('kind')==domain for r in source.get('structured',[]))
        if not re.search(mode,qi.normalized(source.get('titulo',''))) and not structured_trip:
            reasons.append('SOURCE_MISMATCH')
        state='ROUTE_INFORMATION' if not reasons else 'UNVERIFIED'
        trip=next((r for r in source.get('structured',[]) if r.get('kind')==domain),{})
        origin=trip.get('departureAirport') or trip.get('departureBusStop') or ''
        destination=trip.get('arrivalAirport') or trip.get('arrivalBusStop') or ''
        if trip and contains(p.get('origin'),origin) and contains(p.get('destination'),destination):
            data={k:v for k,v in trip.items() if k not in ('declared_price','currency','availability')}
            state='PUBLISHED_SCHEDULE'
            valid_price = False
            try:
                amount = Decimal(str(trip.get('declared_price', '')))
                valid_price = amount.is_finite() and amount > 0 and bool(re.fullmatch('[A-Z]{3}', str(trip.get('currency', ''))))
                expiry = trip.get('validThrough')
                if expiry and date.fromisoformat(str(expiry)[:10]) < date.fromisoformat(request['resolved_at'][:10]):
                    valid_price = False
                    reasons.append('EXPIRED_FARE')
            except (InvalidOperation, ValueError, KeyError):
                valid_price = False
            if p.get('departure_date')==str(trip.get('departureTime',''))[:10] and p.get('adults') and trip.get('adults')==p['adults'] and valid_price:
                state='MATCHED_DECLARED_FARE';data.update(price=str(amount),currency=trip['currency'])
        # No source timestamp/stock verification: never assert current inventory.
        data['inventory_state']='not_verified'
    eligible=not reasons
    retrieval = {'ROUTE_INFORMATION':'ROUTE_FOUND', 'PUBLISHED_SCHEDULE':'SCHEDULE_FOUND',
                 'MATCHED_DECLARED_FARE':'PRICE_FOUND', 'PUBLISHED_REPORT':'ARTICLE_FOUND',
                 'DECLARED_EVENT':'EVENT_DECLARED'}.get(state, 'UNAVAILABLE')
    complete = eligible
    if domain == 'news':
        complete = eligible and bool(data.get('published_at')) and bool(source.get('texto_lido'))
    elif domain == 'events':
        complete = eligible and all(data.get(k) for k in ('name','location','event_date','organizer'))
    elif domain in ('air_travel', 'bus_travel'):
        complete = False  # No adapter here verifies live inventory or sale conditions.
    return {'kind':domain,'url':str(source.get('url') or '')[:500], 'eligible':eligible,'verification':state,
            'retrieval_state': retrieval, 'data_complete': complete, 'required_data': request.get('required_data', []),
            'reasons':list(dict.fromkeys(reasons)),'data':data}
