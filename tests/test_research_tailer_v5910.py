"""Terminal research jobs must release the real event-tailer thread."""
import json,threading
import pytest
import pc_agent
import research_agents as ra


@pytest.mark.parametrize('state',['concluida','cancelada','falhou','interrompida','pausada'])
def test_tailer_flushes_events_and_finishes_inactive_job(tmp_path,state):
    path=tmp_path/'qa.sqlite';db=pc_agent.open_db(path)
    job=ra.criar_job(db,'qa','Research tailer lifecycle',conv='qa')
    ra.emitir(db,job['id'],'qa','qa','research_completed','alerta','QA terminal event',{})
    db.execute('UPDATE research_jobs SET status=? WHERE id=?',(state,job['id']));db.commit();db.close()
    sent=[]
    class Socket:
        def send(self,data):sent.append(json.loads(data))
    stop=threading.Event()
    thread=threading.Thread(target=pc_agent._job_tailer,args=(str(path),job['id'],'qa',Socket(),stop,threading.Event()))
    try:
        thread.start();thread.join(.75)
        assert not thread.is_alive(),f'Terminal state {state} leaked an event tailer'
        assert sent and sent[-1]['event']['tipo']=='research_completed'
        assert all(row['owner']=='qa' and row['job_id']==job['id'] for row in sent)
    finally:stop.set();thread.join(2)


def test_active_tailer_remains_subscribed_until_cancel(tmp_path):
    path=tmp_path/'qa.sqlite';db=pc_agent.open_db(path)
    job=ra.criar_job(db,'qa','Active research tailer',conv='qa')
    ra.emitir(db,job['id'],'qa','qa','step_started','ok','QA active event',{});db.close()
    seen=threading.Event()
    class Socket:
        def send(self,data):seen.set()
    stop=threading.Event()
    thread=threading.Thread(target=pc_agent._job_tailer,args=(str(path),job['id'],'qa',Socket(),stop,threading.Event()))
    try:
        thread.start();assert seen.wait(1);assert thread.is_alive()
    finally:stop.set();thread.join(2)
    assert not thread.is_alive()
