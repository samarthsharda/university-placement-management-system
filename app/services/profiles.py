"""Profile service owns contact data and verified academic revisions."""
from fastapi import APIRouter, Depends, Request
from ..contracts import AcademicUpdate, ContactUpdate
from ..security import current_user, officer, fail
from ..db import audit, now

router=APIRouter(prefix='/v1',tags=['Profile Service'])


def profile(con, student_id):
    row=con.execute('SELECT * FROM profiles WHERE student_id=?',(student_id,)).fetchone()
    if not row:
        fail(404,'Student not found')
    return dict(row)


def present(row):
    return {**row,'cgpa':row['cgpa_hundredths']/100,'verified':bool(row['verified'])}


@router.get('/students')
def students(request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect() as con:
        return [present(dict(r)) for r in con.execute('SELECT * FROM profiles ORDER BY student_id')]


@router.get('/students/me')
def mine(request:Request,user=Depends(current_user)):
    if user['role']!='student': fail(403,'Student access required')
    with request.app.state.db.connect() as con:
        return present(profile(con,user['student_id']))


@router.patch('/students/me')
def contact(data:ContactUpdate,request:Request,user=Depends(current_user)):
    if user['role']!='student': fail(403,'Student access required')
    with request.app.state.db.connect(True) as con:
        con.execute('UPDATE profiles SET email=?,updated_at=? WHERE student_id=?',(data.email,now(),user['student_id']))
        audit(con,user['id'],'ContactUpdated',user['student_id'],{})
        return present(profile(con,user['student_id']))


@router.patch('/students/{student_id}/academic')
def verify(student_id:str,data:AcademicUpdate,request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect(True) as con:
        before=profile(con,student_id)
        if before['version']!=data.expected_version: fail(409,'Academic record changed. Refresh and try again')
        con.execute('UPDATE profiles SET programme=?,graduation_year=?,cgpa_hundredths=?,backlogs=?,verified=?,version=version+1,updated_at=? WHERE student_id=?',
            (data.programme,data.graduation_year,int(data.cgpa*100),data.backlogs,int(data.verified),now(),student_id))
        audit(con,user['id'],'AcademicVersionCreated',student_id,{'previous_version':before['version'],'reason':data.reason})
        return present(profile(con,student_id))
