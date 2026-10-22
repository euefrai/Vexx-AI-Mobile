from datetime import datetime, timezone
import json
import pytest
import jdui
import live_data
import query_intelligence as qi

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('query,domain,date', [
    ('Pesquise voos de Salvador para São Paulo daqui a 30 dias, para um adulto, com o menor preço disponível.', 'air_travel', '2026-11-21'),
    ('Pesquise passagens de ônibus de Salvador para Feira de Santana para daqui a sete dias.', 'bus_travel', '2026-10-29'),
])
def test_relative_trip_dates_and_route_are_frozen_once(query, domain, date):
    result = qi.analyze(query, NOW)
    params = result['parameters']
    assert result['domain'] == domain and params['departure_date'] == date
    assert params['origin'] == 'Salvador'
    assert params['destination'] in ('São Paulo', 'Feira de Santana')
    assert params['inventory_state'] == 'not_verified'
    assert date in result['resolved_request']


def test_ranges_do_not_confuse_publication_and_occurrence():
    news = qi.analyze('O que aconteceu em Salvador nos últimos sete dias?', NOW)
    event = qi.analyze('Quais eventos em Recife nas próximas duas semanas?', NOW)
    assert news['parameters']['start_date'] == '2026-10-15'
    assert event['parameters']['end_date'] == '2026-11-05'
    assert 'event_date' not in news['parameters']
    with pytest.raises(ValueError):
        qi.analyze('voos daqui a 999 dias', NOW)


@pytest.mark.parametrize('query,pair', [('USD/BRL agora', ('USD','BRL')), ('EUR/BRL agora', ('EUR','BRL')), ('BRL/JPY agora', ('BRL','JPY'))])
def test_currency_direction_is_not_inverted(query, pair):
    req = qi.analyze(query, NOW)
    assert (req['parameters']['base'], req['parameters']['quote']) == pair


def _rates(monkeypatch, rows):
    monkeypatch.setattr(live_data, '_cache', {})
    monkeypatch.setattr(live_data.research, '_circuito', {})
    monkeypatch.setattr(live_data.research, 'baixar', lambda url, **kwargs: (url, json.dumps(rows)))


def test_current_reference_rate_preserves_source_date_and_decimal_amount(monkeypatch):
    _rates(monkeypatch, [{'base':'USD', 'quote':'BRL', 'date':'2026-10-21', 'rate':5.12345}])
    data = live_data.exchange_data('Quanto vale 100 dólares em reais agora?', {}, NOW)
    assert data['converted'] == '512.34'  # Decimal half-even, independent of binary floats.
    assert data['rate_date'] == '2026-10-21' and data['rate_time'] is None
    assert data['rate_type'] == 'daily_reference'
    assert data['queried_at'] == NOW.isoformat()
    text = live_data.currency('Quanto vale 100 dólares em reais agora?', {}, NOW)
    assert 'não informado' in text and 'Não é uma oferta bancária' in text
    assert jdui.extrair_fences(text)


@pytest.mark.parametrize('rate,date,base', [(5,'2026-09-01','USD'), (5,'2026-10-23','USD'), (5,'2026-10-21','EUR'), (float('inf'),'2026-10-21','USD'), (-1,'2026-10-21','USD')])
def test_invalid_or_stale_current_rates_are_rejected(monkeypatch, rate, date, base):
    _rates(monkeypatch, [{'base':base, 'quote':'BRL', 'date':date, 'rate':rate}])
    with pytest.raises(ValueError):
        live_data.exchange_data('100 dólares em reais agora', {}, NOW)


def test_historical_chart_uses_only_actual_observations(monkeypatch):
    _rates(monkeypatch, [{'base':'USD','quote':'BRL','date':'2026-10-20','rate':5},
                         {'base':'USD','quote':'BRL','date':'2026-10-21','rate':5.1}])
    text = live_data.currency('Como mudou o dólar em relação ao real nos últimos 30 dias?', {}, NOW)
    msg = json.loads(text.split('```jdui\n')[1].split('```')[0])
    chart = next(b['props'] for b in msg['blocks'] if b.get('component') == 'chart')
    assert chart['labels'] == ['2026-10-20','2026-10-21']
    assert chart['series'][0]['values'] == [5,5.1]
    assert live_data.request('Quanto vale 100 dólares em reais agora?')['kind'] == 'currency'
