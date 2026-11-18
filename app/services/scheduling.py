"""Scheduling owns half-open interval reservations with serialized conflict checks."""
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,Request
from ..contracts import InterviewCreate
from ..security import current_user,staff,fail,get_record
from ..db import audit,emit,identifier,now
from .applications import application_access

router=APIRouter(prefix='/v1/interviews',tags=['Scheduling Service'])


@router.get('')
def listing(request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        rows=con.execute('SELECT i.*,p.name AS student_name,d.title AS drive_title FROM interviews i JOIN profiles p ON p.student_id=i.student_id JOIN drives d ON d.id=i.drive_id WHERE ?=\'officer\' OR (?=\'student\' AND i.student_id=?) OR (?=\'recruiter\' AND d.company_id=?) ORDER BY i.start',
            (user['role'],user['role'],user['student_id'],user['role'],user['company_id'])).fetchall()
        return [dict(r) for r in rows]


@router.post('',status_code=201)
def create(data:InterviewCreate,request:Request,user=Depends(current_user)):
    staff(user)
    if data.start>=data.end or data.start<=datetime.now(timezone.utc): fail(400,'Choose a future start before the end time')
    start,end=data.start.isoformat(),data.end.isoformat()
    with request.app.state.db.connect(True) as con:
        app=get_record(con,'applications',data.application_id); application_access(con,user,app)
        if app['status']!='SHORTLISTED': fail(409,'Shortlist the application before scheduling')
        conflict=con.execute("SELECT id FROM interviews WHERE status='CONFIRMED' AND start<? AND end>? AND (student_id=? OR lower(interviewer)=lower(?) OR lower(room)=lower(?))",
            (end,start,app['student_id'],data.interviewer,data.room)).fetchone()
        if conflict: fail(409,'Interview conflicts with an existing student, interviewer or room booking')
        iid=identifier('I')
        con.execute('INSERT INTO interviews VALUES(?,?,?,?,?,?,?,?,?,?)',
            (iid,app['id'],app['student_id'],app['drive_id'],data.interviewer,data.room,start,end,'CONFIRMED',now()))
        emit(con,'InterviewScheduled',{'id':iid,'student_id':app['student_id'],'drive_id':app['drive_id'],'start':start})
        audit(con,user['id'],'InterviewScheduled',iid,{'application_id':app['id']})
        return dict(get_record(con,'interviews',iid))


@router.delete('/{interview_id}')
def cancel(interview_id:str,request:Request,user=Depends(current_user)):
    staff(user)
    with request.app.state.db.connect(True) as con:
        interview=get_record(con,'interviews',interview_id)
        application_access(con,user,get_record(con,'applications',interview['application_id']))
        if interview['status']!='CONFIRMED': fail(409,'Interview already cancelled')
        con.execute("UPDATE interviews SET status='CANCELLED' WHERE id=?",(interview_id,))
        emit(con,'InterviewCancelled',{'id':interview_id,'student_id':interview['student_id'],'drive_id':interview['drive_id']})
        audit(con,user['id'],'InterviewCancelled',interview_id,{})
        return {'status':'CANCELLED'}
