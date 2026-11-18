"""Drive management owns approved opportunities and immutable policy versions."""
import json
from fastapi import APIRouter,Depends,Request
from ..contracts import DriveCreate,DriveState
from ..security import current_user,officer,staff,drive_access,get_record,fail
from ..db import audit,now,identifier

router=APIRouter(prefix='/v1/drives',tags=['Drive Management Service'])


def present(row):
    d=dict(row); d['programmes']=json.loads(d['programmes']); d['minimum_cgpa']=d['minimum_cgpa']/100
    return d


@router.get('')
def listing(request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        rows=con.execute('SELECT * FROM drives ORDER BY created_at,id').fetchall()
    return [present(r) for r in rows if (user['role']=='officer' or
        (user['role']=='recruiter' and user['company_id']==r['company_id']) or
        (user['role']=='student' and r['status']!='DRAFT'))]


@router.post('',status_code=201)
def create(data:DriveCreate,request:Request,user=Depends(current_user)):
    staff(user)
    if user['role']=='officer': fail(403,'Create a draft using a recruiter account, then approve as officer')
    company='Northstar Technologies' if user['company_id']=='C01' else 'Vertex Labs'
    did=identifier('D')
    with request.app.state.db.connect(True) as con:
        con.execute('INSERT INTO drives VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (did,data.title,company,user['company_id'],'DRAFT',json.dumps(sorted(set(data.programmes))),data.graduation_year,
             int(data.minimum_cgpa*100),data.maximum_backlogs,data.deadline.isoformat(),1,data.location,now()))
        audit(con,user['id'],'DriveDrafted',did,{'title':data.title})
        return present(get_record(con,'drives',did))


@router.patch('/{drive_id}/status')
def publish(drive_id:str,data:DriveState,request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect(True) as con:
        row=get_record(con,'drives',drive_id)
        if row['policy_version']!=data.expected_version: fail(409,'Drive version changed')
        if (row['status'],data.status) not in [('DRAFT','PUBLISHED'),('PUBLISHED','CLOSED')]: fail(409,'Invalid drive transition')
        if data.status=='PUBLISHED' and row['deadline']<=now(): fail(409,'Cannot publish an expired drive')
        con.execute('UPDATE drives SET status=?,policy_version=policy_version+1 WHERE id=?',(data.status,drive_id))
        audit(con,user['id'],'Drive'+data.status.title(),drive_id,{})
        return present(get_record(con,'drives',drive_id))
