"""All legacy HTTP admin routes deny a valid admin without recent reauth."""
import pytest
from fastapi.testclient import TestClient
import server
from test_admin_v5981 import env, login


@pytest.mark.parametrize('method,path,body',[
    ('GET','/api/admin/users',None),('GET','/api/admin/quality/runs',None),
    ('GET','/api/admin/invites',None),('GET','/api/admin/regs',None),
    ('GET','/api/admin/config',None),('GET','/api/admin/audit',None),
    ('POST','/api/admin/users/create',{'display':'QA account','username':'qa-user','password':'fixture-only-password'}),
    ('POST','/api/admin/users/role',{'uid':'qa-target','role':'admin'}),
    ('POST','/api/admin/users/status',{'uid':'qa-target','status':'bloqueado'}),
    ('POST','/api/admin/users/sessions',{'uid':'qa-target'}),
    ('POST','/api/admin/users/delete',{'uid':'qa-target'}),
    ('POST','/api/admin/users/limits',{'uid':'qa-target','max_ai_hora':1}),
    ('POST','/api/admin/quality/run',{}),('POST','/api/admin/invites/create',{'max_usos':1,'dias':1}),
    ('POST','/api/admin/invites/revoke',{'id':1,'aprovar':False}),
    ('POST','/api/admin/regs/decide',{'id':1,'aprovar':True}),
    ('POST','/api/admin/config',{'modo':'aberto'}),
])
def test_legacy_endpoint_cannot_bypass_recent_authorization(env,method,path,body):
    with TestClient(server.app) as client:
        headers=login(client)
        response=client.request(method,path,json=body,headers=headers)
        assert response.status_code==403,response.text
        assert 'Reautenticação' in response.text
        assert not any(call['type'] in ('admin_create','admin_role','admin_status','admin_delete','quality_run','admin_limits') for call in env.calls)
