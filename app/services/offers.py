"""Offer management owns student acceptance and the one-accepted-offer invariant."""
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,Request
from ..contracts import OfferCreate,OfferDecision
from ..security import current_user,staff,fail,get_record
from ..db import audit,emit,identifier,now
from .applications import application_access

router=APIRouter(prefix='/v1/offers',tags=['Offer Management Service'])


@router.get('')
def listing(request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        rows=con.execute('SELECT o.*,p.name AS student_name,d.company FROM offers o JOIN profiles p ON p.student_id=o.student_id JOIN drives d ON d.id=o.drive_id WHERE ?=\'officer\' OR (?=\'student\' AND o.student_id=?) OR (?=\'recruiter\' AND d.company_id=?) ORDER BY o.created_at DESC',
            (user['role'],user['role'],user['student_id'],user['role'],user['company_id'])).fetchall()
        return [dict(r) for r in rows]


@router.post('',status_code=201)
def issue(data:OfferCreate,request:Request,user=Depends(current_user)):
    staff(user)
    with request.app.state.db.connect(True) as con:
        app=get_record(con,'applications',data.application_id); application_access(con,user,app)
        if app['status']!='SELECTED': fail(409,'Select the student before issuing an offer')
        if con.execute('SELECT id FROM offers WHERE application_id=?',(app['id'],)).fetchone(): fail(409,'An offer already exists for this application')
        oid=identifier('O'); drive=get_record(con,'drives',app['drive_id'])
        con.execute('INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?)',
            (oid,app['id'],app['student_id'],app['drive_id'],drive['title'],'ISSUED',data.expires_at.isoformat(),now(),1))
        emit(con,'OfferIssued',{'id':oid,'student_id':app['student_id'],'drive_id':app['drive_id'],'status':'ISSUED'})
        audit(con,user['id'],'OfferIssued',oid,{'application_id':app['id']})
        return dict(get_record(con,'offers',oid))


@router.post('/{offer_id}/decisions')
def decide(offer_id:str,data:OfferDecision,request:Request,user=Depends(current_user)):
    with request.app.state.db.connect(True) as con:
        offer=get_record(con,'offers',offer_id)
        application_access(con,user,get_record(con,'applications',offer['application_id']))
        if user['role']=='student' and data.status=='REVOKED': fail(403,'Students cannot revoke offers')
        if user['role']!='student' and data.status!='REVOKED': fail(403,'Only the student can accept or decline an offer')
        if offer['version']!=data.expected_version: fail(409,'Offer changed. Refresh and try again')
        allowed = offer['status']=='ISSUED' or (data.status=='REVOKED' and offer['status']=='ACCEPTED')
        if not allowed: fail(409,'This offer cannot change to the requested state')
        if data.status in ('ACCEPTED','DECLINED') and offer['expires_at']<=now(): fail(409,'The offer has expired')
        if data.status=='ACCEPTED' and con.execute("SELECT id FROM offers WHERE student_id=? AND status='ACCEPTED'",(offer['student_id'],)).fetchone():
            fail(409,'One-offer policy: another offer is already accepted')
        con.execute('UPDATE offers SET status=?,version=version+1 WHERE id=?',(data.status,offer_id))
        emit(con,'OfferDecided',{'id':offer_id,'student_id':offer['student_id'],'drive_id':offer['drive_id'],'status':data.status})
        audit(con,user['id'],'Offer'+data.status.title(),offer_id,{})
        return dict(get_record(con,'offers',offer_id))
