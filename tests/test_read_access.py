"""Real thread coordination with controlled transports; no external inference."""
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from urllib.error import HTTPError

import pytest
import read_access
import research
import retrieval_trace


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(read_access, 'public_reads', read_access.Coordinator())
    monkeypatch.setattr(research, '_ips_globais', lambda host: None)


def response(body=b'<main><p>Readable public content.</p></main>', status=200, headers=None):
    result = io.BytesIO(body)
    result.status = status
    result.headers = Message()
    result.headers['Content-Type'] = 'text/html; charset=utf-8'
    for key, value in (headers or {}).items():
        result.headers[key] = value
    return result


@pytest.mark.parametrize('status,reason', [(401,'authentication_required'),(403,'access_denied'),
    (429,'rate_limited'),(503,'service_unavailable'),(404,'not_found')])
@pytest.mark.parametrize('raised', [False, True])
def test_statuses_preserve_specific_reason_and_retry_after(status, reason, raised):
    def open_url(url, *args):
        if raised:
            raise HTTPError(url,status,'failure',{'Retry-After':'90'},None)
        return response(status=status,headers={'Retry-After':'90'})
    with retrieval_trace.observe() as rows, retrieval_trace.source_scope('job','step',{'url':'https://public.example/a'}):
        with pytest.raises(research.ResearchErro) as caught:
            research.baixar('https://public.example/a',abrir=open_url)
    assert caught.value.http==status and caught.value.access_reason==reason
    assert caught.value.retry_after==90
    assert rows[-1]['reason_code']==reason.upper()
    assert 'failure' not in str(caught.value)


def test_retry_after_date_and_invalid_values():
    later=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=60),usegmt=True)
    assert 58<=read_access.retry_after({'Retry-After':later})<=60
    for value in ('NaN','inf','-1','1.5','x'*150,''):
        assert read_access.retry_after({'Retry-After':value}) is None
    assert read_access.retry_after({'Retry-After':'0'})==0


def test_429_defers_same_origin_without_sleep_or_blocking_other_hosts():
    calls=[]
    def open_url(url,*args):
        calls.append(url)
        if len(calls)==1:raise HTTPError(url,429,'limit',{'Retry-After':'120'},None)
        return response()
    with pytest.raises(research.ResearchErro):research.baixar('https://a.example/x',abrir=open_url)
    with pytest.raises(research.ResearchErro) as caught:
        research.baixar('https://a.example/y',abrir=open_url)
    assert caught.value.access_reason=='rate_limited' and caught.value.retry_after>119
    assert research.baixar('https://b.example/x',abrir=open_url)[1]
    assert len(calls)==2


def test_403_only_defers_protected_url_and_expiry_recovers(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr(read_access.time,'monotonic',lambda:clock[0])
    calls=[]
    def open_url(url,*args):
        calls.append(url)
        if len(calls)==1:raise HTTPError(url,403,'denied',{},None)
        return response()
    with pytest.raises(research.ResearchErro):research.baixar('https://a.example/private',abrir=open_url)
    with pytest.raises(research.ResearchErro):research.baixar('https://a.example/private',abrir=open_url)
    assert research.baixar('https://a.example/public',abrir=open_url)[1]
    clock[0]+=16
    assert research.baixar('https://a.example/private',abrir=open_url)[1]
    assert len(calls)==3


def test_identical_inflight_read_is_joined_but_completed_body_is_not_cached():
    entered=threading.Event();release=threading.Event();joined=threading.Event();calls=[]
    def open_url(url,*args):
        calls.append(url);entered.set();assert release.wait(2)
        return response()
    def second():
        joined.set()
        return research.baixar('https://a.example/x',abrir=open_url)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one=pool.submit(research.baixar,'https://a.example/x',abrir=open_url)
        assert entered.wait(1)
        two=pool.submit(second);assert joined.wait(1)
        # Wait until the second thread has entered the coordinator condition.
        import time
        time.sleep(.03)
        release.set()
        assert one.result()==two.result() and len(calls)==1
    research.baixar('https://a.example/x',abrir=open_url)
    assert len(calls)==2


def test_queue_cancellation_and_short_deadline_do_not_cancel_leader():
    entered=threading.Event();release=threading.Event();cancel=threading.Event()
    gate=read_access.Coordinator(per_origin=1)
    def operation(remaining):
        entered.set();assert release.wait(2);return 'ok'
    with ThreadPoolExecutor(max_workers=2) as pool:
        leader=pool.submit(gate.run,'https://a.example/x',(),2,operation)
        assert entered.wait(1)
        with pytest.raises(read_access.Deferred,match='read_budget_exhausted'):
            gate.run('https://a.example/y',(),.02,lambda left:pytest.fail('queue leaked'))
        cancel.set()
        with pytest.raises(read_access.Deferred) as caught:
            gate.run('https://a.example/x',(),1,lambda left:None,cancelled=cancel.is_set)
        assert caught.value.codigo=='cancelada'
        release.set();assert leader.result()=='ok'
    assert not gate._active and not gate._flights


def test_waiting_duplicate_can_cancel_without_stopping_other_consumers():
    gate=read_access.Coordinator();entered=threading.Event();release=threading.Event()
    cancel=threading.Event();timer=threading.Timer(.04,cancel.set)
    def operation(left):entered.set();assert release.wait(2);return 'ok'
    with ThreadPoolExecutor(max_workers=2) as pool:
        leader=pool.submit(gate.run,'https://a.example/x',(),1,operation)
        assert entered.wait(1)
        timer.start()
        try:
            with pytest.raises(read_access.Deferred) as caught:
                gate.run('https://a.example/x',(),.8,lambda left:pytest.fail('duplicate request'),cancelled=cancel.is_set)
            assert caught.value.codigo=='cancelada'
        finally:release.set();timer.cancel()
        assert leader.result()=='ok'


def test_origin_limit_and_deferred_state_are_bounded():
    gate=read_access.Coordinator(per_origin=2,max_entries=2)
    entered=threading.Event();release=threading.Event();lock=threading.Lock();active=[0];peak=[0]
    def operation(left):
        with lock:
            active[0]+=1;peak[0]=max(peak[0],active[0])
            if active[0]==2:entered.set()
        assert release.wait(2)
        with lock:active[0]-=1
        return 'ok'
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(gate.run,'https://a.example/'+str(i),(),1,operation) for i in range(3)]
        assert entered.wait(1);release.set()
        assert [future.result() for future in futures]==['ok']*3 and peak[0]==2
    for index in range(3):
        def limited(left):raise research._http_read_error(429,{'Retry-After':'30'})
        with pytest.raises(research.ResearchErro):gate.run('https://a'+str(index)+'.example/x',(),1,limited)
    assert len(gate._deferred)==2 and not gate._active and not gate._flights


def test_leader_cancellation_after_download_does_not_discard_another_consumers_result():
    gate=read_access.Coordinator();entered=threading.Event();release=threading.Event()
    joined=threading.Event();cancel_leader=threading.Event();calls=[]
    def operation(left):
        calls.append(1);entered.set();assert release.wait(2);return 'public document'
    def follower_cancelled():joined.set();return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        leader=pool.submit(gate.run,'https://a.example/x',(),1,operation,cancelled=cancel_leader.is_set)
        assert entered.wait(1)
        follower=pool.submit(gate.run,'https://a.example/x',(),1,
                             lambda left:pytest.fail('duplicate'),cancelled=follower_cancelled)
        assert joined.wait(1)
        cancel_leader.set();release.set()
        with pytest.raises(read_access.Deferred) as caught:leader.result()
        assert caught.value.codigo=='cancelada'
        assert follower.result()=='public document' and calls==[1]


def test_redirect_uses_destination_origin_policy_and_revalidates_ssrf(monkeypatch):
    calls=[]
    def open_url(url,*args):
        calls.append(url)
        if url.endswith('/redirect'):raise HTTPError(url,302,'redirect',{'Location':'https://b.example/limited'},None)
        if url.endswith('/limited'):raise HTTPError(url,429,'limit',{'Retry-After':'90'},None)
        return response()
    with pytest.raises(research.ResearchErro):research.baixar('https://a.example/redirect',abrir=open_url)
    with pytest.raises(research.ResearchErro):research.baixar('https://b.example/other',abrir=open_url)
    assert research.baixar('https://a.example/public',abrir=open_url)[1]
    assert len(calls)==3
    def check(host):
        if host=='b.example':raise research.ResearchErro('Private address','ssrf')
    monkeypatch.setattr(research,'_ips_globais',check)
    with pytest.raises(research.ResearchErro) as caught:
        research.baixar('https://a.example/redirect',abrir=open_url)
    assert caught.value.codigo=='ssrf'


def test_challenge_is_observed_separately_from_forbidden_and_timeout():
    body=b'<html><title>Just a moment...</title><body><div id="cf-chl-widget">Verify you are human</div></body></html>'
    with pytest.raises(research.ResearchErro) as caught:
        research.baixar('https://a.example/challenge',abrir=lambda *args:response(body))
    assert caught.value.access_reason=='challenge_required'
    def timeout(*args):raise TimeoutError()
    with pytest.raises(research.ResearchErro) as caught:
        research.baixar('https://a.example/slow',abrir=timeout)
    assert caught.value.codigo=='rede' and caught.value.access_reason=='fetch_timeout'
