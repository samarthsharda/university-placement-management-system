"""Acceptance checks derived from the report, including real concurrent calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Barrier
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def system(tmp_path):
    app=create_app(tmp_path/'placement.sqlite3')
    with TestClient(app) as client:
        yield app,client


def headers(client,email='officer@demo.edu'):
    response=client.post('/v1/auth/login',json={'email':email,'password':'Placement@123'})
    assert response.status_code==200,response.text
    return {'Authorization':'Bearer '+response.json()['token']}


def apply(client,student='s01',drive='D101',key=None):
    return client.post(f'/v1/drives/{drive}/applications',json={},
                       headers={**headers(client,student+'@demo.edu'),'Idempotency-Key':key or student+'-'+drive+'-request-001'})


def select(client,aid,staff):
    for version,status in [(1,'SHORTLISTED'),(2,'SELECTED')]:
        result=client.patch('/v1/applications/'+aid+'/status',headers=staff,json={'status':status,'expected_version':version})
        assert result.status_code==200,result.text


def issue(client,aid,staff):
    return client.post('/v1/offers',headers=staff,json={'application_id':aid,'expires_at':(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()})


def test_T1_T2_report_cohort_and_exact_boundary(system):
    _,c=system; h=headers(c)
    results=[c.post('/v1/eligibility/evaluations',headers=h,json={'drive_id':'D101','student_id':f'S{i:02}'}).json() for i in range(1,7)]
    assert [r['decision'] for r in results]==['ELIGIBLE','ELIGIBLE','INELIGIBLE','INELIGIBLE','INELIGIBLE','REVIEW_REQUIRED']
    assert results[1]['academic_snapshot']['cgpa_hundredths']==700
    assert results[5]['reasons']==['ACADEMIC_UNVERIFIED']


def test_invalid_login_and_session_revocation(system):
    _,c=system
    assert c.get('/v1/drives').status_code==401
    assert c.post('/v1/auth/login',json={'email':'officer@demo.edu','password':'wrong'}).status_code==401
    h=headers(c); assert c.post('/v1/auth/logout',headers=h).status_code==200
    assert c.get('/v1/drives',headers=h).status_code==401


def test_T3_concurrent_duplicate_different_keys(system):
    app,c=system; h=headers(c,'s01@demo.edu'); barrier=Barrier(2)
    def submit(n):
        with TestClient(app) as own:
            barrier.wait()
            return own.post('/v1/drives/D101/applications',headers={**h,'Idempotency-Key':'concurrent-key-'+str(n)},json={}).status_code
    with ThreadPoolExecutor(2) as pool: statuses=list(pool.map(submit,[1,2]))
    assert sorted(statuses)==[201,409]
    with app.state.db.connect() as con:
        assert con.execute('SELECT count(*) FROM applications').fetchone()[0]==1
        assert con.execute("SELECT count(*) FROM outbox WHERE event_type='ApplicationSubmitted'").fetchone()[0]==1


def test_T4_idempotent_retry_and_key_content_conflict(system):
    _,c=system; h=headers(c,'s01@demo.edu'); h['Idempotency-Key']='stable-request-key'
    first=c.post('/v1/drives/D101/applications',headers=h,json={})
    retry=c.post('/v1/drives/D101/applications',headers=h,json={})
    assert first.status_code==201 and retry.status_code==200
    assert first.json()['id']==retry.json()['id']
    assert retry.headers['Idempotent-Replayed']=='true'
    assert c.post('/v1/drives/D101/applications',headers=h,json={'resume_version':'different'}).status_code==409


def test_T5_T6_outage_dead_letter_recovery_and_replay(system):
    app,c=system; staff=headers(c); response=apply(c); assert response.status_code==201
    c.patch('/v1/simulation',headers=staff,json={'notification_outage':True})
    for _ in range(3): assert c.post('/v1/events/process',headers=staff).json()['failed']==1
    event=c.get('/v1/events',headers=staff).json()[0]
    assert event['status']=='DEAD' and event['consumers']==['reporting']
    report=c.get('/v1/reports/placements',headers=staff).json()
    assert report['applications']==1 and report['as_of'] is not None
    assert len(c.get('/v1/applications',headers=staff).json())==1
    c.patch('/v1/simulation',headers=staff,json={'notification_outage':False})
    c.post('/v1/events/'+event['id']+'/replay',headers=staff)
    assert c.post('/v1/events/process',headers=staff).json()['consumer_effects']==1
    c.post('/v1/events/'+event['id']+'/replay',headers=staff)
    assert c.post('/v1/events/process',headers=staff).json()['consumer_effects']==0
    with app.state.db.connect() as con:
        assert con.execute('SELECT count(*) FROM notifications').fetchone()[0]==1
        assert con.execute('SELECT count(*) FROM application_projection').fetchone()[0]==1


def test_T7_recruiter_scope_and_student_cannot_escalate(system):
    _,c=system; app=apply(c).json(); other=headers(c,'recruiter2@demo.edu'); student=headers(c,'s02@demo.edu')
    assert c.get('/v1/applications/'+app['id'],headers=other).status_code==403
    assert c.get('/v1/applications',headers=other).json()==[]
    assert c.get('/v1/applications/'+app['id'],headers=student).status_code==403
    assert c.get('/v1/students',headers=student).status_code==403
    assert c.post('/v1/events/process',headers=student).status_code==403
    assert c.patch('/v1/applications/'+app['id']+'/status',headers=headers(c,'s01@demo.edu'),json={'status':'SELECTED','expected_version':1}).status_code==403


def test_T8_concurrent_calendar_conflict_and_adjacent_intervals(system):
    app,c=system; staff=headers(c); aids=[apply(c,s).json()['id'] for s in ['s01','s02']]
    for aid in aids: assert c.patch('/v1/applications/'+aid+'/status',headers=staff,json={'status':'SHORTLISTED','expected_version':1}).status_code==200
    start=datetime.now(timezone.utc)+timedelta(days=2); end=start+timedelta(minutes=30); barrier=Barrier(2)
    def reserve(aid):
        with TestClient(app) as own:
            barrier.wait()
            return own.post('/v1/interviews',headers=staff,json={'application_id':aid,'start':start.isoformat(),'end':end.isoformat(),'room':'Room A','interviewer':'panel@demo.edu'})
    with ThreadPoolExecutor(2) as pool: responses=list(pool.map(reserve,aids))
    assert sorted(r.status_code for r in responses)==[201,409]
    losing=aids[[r.status_code for r in responses].index(409)]
    assert c.post('/v1/interviews',headers=staff,json={'application_id':losing,'start':end.isoformat(),'end':(end+timedelta(minutes=30)).isoformat(),'room':'Room A','interviewer':'panel@demo.edu'}).status_code==201


def test_T9_concurrent_offer_acceptance(system):
    app,c=system; staff=headers(c); student=headers(c,'s01@demo.edu')
    c.patch('/v1/drives/D102/status',headers=staff,json={'status':'PUBLISHED','expected_version':1})
    offers=[]
    for drive in ['D101','D102']:
        aid=apply(c,drive=drive).json()['id']; select(c,aid,staff); offers.append(issue(c,aid,staff).json()['id'])
    barrier=Barrier(2)
    def accept(oid):
        with TestClient(app) as own:
            barrier.wait()
            return own.post('/v1/offers/'+oid+'/decisions',headers=student,json={'status':'ACCEPTED','expected_version':1}).status_code
    with ThreadPoolExecutor(2) as pool: responses=list(pool.map(accept,offers))
    assert sorted(responses)==[200,409]
    with app.state.db.connect() as con: assert con.execute("SELECT count(*) FROM offers WHERE status='ACCEPTED'").fetchone()[0]==1


def test_report_arithmetic_and_projection_lag(system):
    _,c=system; staff=headers(c); offer_ids=[]
    for s in ['s01','s02']:
        aid=apply(c,s).json()['id']; select(c,aid,staff); offer_ids.append(issue(c,aid,staff).json()['id'])
    for student,oid,status in zip(['s01','s02'],offer_ids,['ACCEPTED','DECLINED']):
        assert c.post('/v1/offers/'+oid+'/decisions',headers=headers(c,student+'@demo.edu'),json={'status':status,'expected_version':1}).status_code==200
    before=c.get('/v1/reports/placements',headers=staff).json(); assert before['placed']==0 and before['reporting_lag']>0
    c.post('/v1/events/process',headers=staff)
    r=c.get('/v1/reports/placements',headers=staff).json()
    assert (r['cohort'],r['applications'],r['offers'],r['placed'])==(6,2,2,1)
    assert r['acceptance_rate']==50 and r['placement_rate']==16.7
    assert r['reconciliation']['matched'] and r['reporting_lag']==0
    assert '16.7' in c.get('/v1/reports/placements.csv',headers=staff).text


def test_snapshot_immutable_after_academic_correction(system):
    _,c=system; staff=headers(c); original=apply(c).json(); s=c.get('/v1/students',headers=staff).json()[0]
    correction={'programme':'CSE','graduation_year':2027,'cgpa':6.5,'backlogs':0,'verified':True,'expected_version':s['version'],'reason':'Corrected verified academic feed'}
    assert c.patch('/v1/students/S01/academic',headers=staff,json=correction).status_code==200
    assert c.patch('/v1/students/S01/academic',headers=staff,json=correction).status_code==409
    assert c.get('/v1/applications/'+original['id'],headers=staff).json()['snapshot']==original['snapshot']
    assert c.post('/v1/eligibility/evaluations',headers=staff,json={'student_id':'S01','drive_id':'D101'}).json()['decision']=='INELIGIBLE'


def test_draft_approval_closure_and_recruiter_creation(system):
    _,c=system; student=headers(c,'s01@demo.edu'); staff=headers(c)
    assert [d['id'] for d in c.get('/v1/drives',headers=student).json()]==['D101']
    assert c.post('/v1/eligibility/evaluations',headers=student,json={'drive_id':'D102'}).status_code==404
    assert c.patch('/v1/drives/D102/status',headers=student,json={'status':'PUBLISHED','expected_version':1}).status_code==403
    assert c.patch('/v1/drives/D101/status',headers=staff,json={'status':'CLOSED','expected_version':1}).status_code==200
    assert apply(c).status_code==409
    r=c.post('/v1/drives',headers=headers(c,'recruiter@demo.edu'),json={'title':'Backend Developer','programmes':['CSE'],'graduation_year':2027,'minimum_cgpa':7,'maximum_backlogs':0,'deadline':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(),'location':'Chennai'})
    assert r.status_code==201 and r.json()['status']=='DRAFT'


def test_invalid_state_changes_and_expired_offer(system):
    app,c=system; staff=headers(c); aid=apply(c).json()['id']
    assert c.patch('/v1/applications/'+aid+'/status',headers=staff,json={'status':'SELECTED','expected_version':1}).status_code==409
    assert issue(c,aid,staff).status_code==409
    select(c,aid,staff); oid=issue(c,aid,staff).json()['id']
    with app.state.db.connect(True) as con: con.execute('UPDATE offers SET expires_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),oid))
    assert c.post('/v1/offers/'+oid+'/decisions',headers=headers(c,'s01@demo.edu'),json={'status':'ACCEPTED','expected_version':1}).status_code==409


def test_private_resume_and_upload_validation(system):
    _,c=system; s01=headers(c,'s01@demo.edu'); s02=headers(c,'s02@demo.edu')
    assert c.post('/v1/resumes',headers=s01,content=b'not a pdf').status_code==400
    assert c.post('/v1/resumes',headers=s01,content=b'%PDF-'+b'x'*(2*1024*1024)).status_code==413
    resume=c.post('/v1/resumes?name=cv.pdf',headers=s01,content=b'%PDF-1.4\n%%EOF').json()['id']
    assert c.get('/v1/resumes/'+resume,headers=s02).status_code==403
    recruiter=headers(c,'recruiter@demo.edu')
    assert c.get('/v1/resumes/'+resume,headers=recruiter).status_code==403
    assert c.post('/v1/drives/D101/applications',headers={**s01,'Idempotency-Key':'resume-request-001'},json={'resume_version':resume}).status_code==201
    assert c.get('/v1/resumes/'+resume,headers=recruiter).status_code==200
    assert c.get('/v1/resumes/'+resume,headers=headers(c,'recruiter2@demo.edu')).status_code==403


def test_persistence_between_app_instances(system):
    app,c=system; aid=apply(c).json()['id']; another=create_app(app.state.db.path)
    with TestClient(another) as second:
        assert second.get('/v1/applications/'+aid,headers=headers(second)).json()['id']==aid


def test_service_catalogue_and_validation(system):
    _,c=system; h=headers(c)
    assert len(c.get('/v1/services',headers=h).json()['services'])==8
    response=c.post('/v1/auth/login',json={'email':'x','password':'p','role':'officer'})
    assert response.status_code==422 and response.headers['content-type'].startswith('application/problem+json')
    assert '/v1/eligibility/evaluations' in c.get('/openapi.json').json()['paths']


def test_reporting_filters_to_current_2027_cohort(system):
    app,c=system; staff=headers(c); aid=apply(c).json()['id']; select(c,aid,staff)
    oid=issue(c,aid,staff).json()['id']
    c.post('/v1/offers/'+oid+'/decisions',headers=headers(c,'s01@demo.edu'),json={'status':'ACCEPTED','expected_version':1})
    c.post('/v1/events/process',headers=staff)
    with app.state.db.connect(True) as con: con.execute("UPDATE profiles SET graduation_year=2028 WHERE student_id='S01'")
    result=c.get('/v1/reports/placements',headers=staff).json()
    assert (result['cohort'],result['applications'],result['offers'],result['placed'])==(5,0,0,0)
    assert result['reconciliation']['matched']
