"""Application service stores immutable evidence and a transactional outbox."""
import hashlib
import json
from fastapi import APIRouter,Depends,Header,Request,Response
from ..contracts import Submission,ApplicationState
from ..security import current_user,drive_access,get_record,fail
from ..db import audit,emit,identifier,now
from .eligibility import evaluate

router=APIRouter(prefix='/v1',tags=['Application Service'])


def application_access(con,user,app):
    if user['role']=='student':
        if user['student_id']!=app['student_id']: fail(403,'This application belongs to another student')
    else:
        drive_access(user,get_record(con,'drives',app['drive_id']))


def present(con,row):
    d=dict(row); d['snapshot']=json.loads(d['snapshot'])
    student=d['snapshot']['academic_snapshot']; drive=get_record(con,'drives',d['drive_id'])
    d.update(student_name=student['name'],drive_title=drive['title'],company=drive['company'])
    return d


@router.get('/applications')
def listing(request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        rows=con.execute('SELECT a.* FROM applications a JOIN drives d ON d.id=a.drive_id WHERE ?=\'officer\' OR (?=\'student\' AND a.student_id=?) OR (?=\'recruiter\' AND d.company_id=?) ORDER BY a.created_at DESC',
            (user['role'],user['role'],user['student_id'],user['role'],user['company_id'])).fetchall()
        return [present(con,r) for r in rows]


@router.get('/applications/{application_id}')
def detail(application_id:str,request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        row=get_record(con,'applications',application_id); application_access(con,user,row)
        return present(con,row)


@router.post('/drives/{drive_id}/applications',status_code=201)
def submit(drive_id:str,data:Submission,request:Request,response:Response,
           idempotency_key:str=Header(min_length=8,max_length=120),user=Depends(current_user)):
    if user['role']!='student': fail(403,'Student access required')
    digest=hashlib.sha256(json.dumps({'drive':drive_id,**data.model_dump()},sort_keys=True).encode()).hexdigest()
    with request.app.state.db.connect(True) as con:
        prior=con.execute('SELECT * FROM idempotency WHERE principal=? AND key=?',(user['id'],idempotency_key)).fetchone()
        if prior:
            if prior['digest']!=digest: fail(409,'This idempotency key was used with different content')
            response.status_code=200; response.headers['Idempotent-Replayed']='true'
            return present(con,get_record(con,'applications',prior['application_id']))
        existing=con.execute('SELECT * FROM applications WHERE student_id=? AND drive_id=?',(user['student_id'],drive_id)).fetchone()
        if existing: fail(409,'You already have an application for this drive')
        drive=get_record(con,'drives',drive_id)
        if drive['status']=='DRAFT': fail(404,'Drive not found')
        decision=evaluate(con,user['student_id'],drive)
        if decision['decision']!='ELIGIBLE': fail(409,{'message':'Eligibility requirements are not met','decision':decision})
        if data.resume_version:
            resume=get_record(con,'resumes',data.resume_version)
            if resume['student_id']!=user['student_id']: fail(403,'This resume belongs to another student')
        aid=identifier('A')
        con.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?)',
            (aid,user['student_id'],drive_id,'SUBMITTED',json.dumps(decision),data.resume_version,now(),1))
        con.execute('INSERT INTO idempotency VALUES(?,?,?,?,?)',(user['id'],idempotency_key,drive_id,digest,aid))
        emit(con,'ApplicationSubmitted',{'id':aid,'student_id':user['student_id'],'drive_id':drive_id,'status':'SUBMITTED'})
        audit(con,user['id'],'ApplicationSubmitted',aid,{'academic_version':decision['academic_version'],'policy_version':decision['policy_version']})
        response.headers['Location']='/v1/applications/'+aid
        return present(con,get_record(con,'applications',aid))


@router.patch('/applications/{application_id}/status')
def transition(application_id:str,data:ApplicationState,request:Request,user=Depends(current_user)):
    with request.app.state.db.connect(True) as con:
        app=get_record(con,'applications',application_id); application_access(con,user,app)
        if user['role']=='student' and data.status!='WITHDRAWN': fail(403,'Only staff can record selection decisions')
        if app['version']!=data.expected_version: fail(409,'Application changed. Refresh and try again')
        allowed={'SUBMITTED':['SHORTLISTED','REJECTED','WITHDRAWN'],'SHORTLISTED':['SELECTED','REJECTED','WITHDRAWN']}
        if data.status not in allowed.get(app['status'],[]): fail(409,'Invalid application state transition')
        con.execute('UPDATE applications SET status=?,version=version+1 WHERE id=?',(data.status,application_id))
        emit(con,'ApplicationChanged',{'id':app['id'],'student_id':app['student_id'],'drive_id':app['drive_id'],'status':data.status})
        audit(con,user['id'],'Application'+data.status.title(),application_id,{})
        return present(con,get_record(con,'applications',application_id))
