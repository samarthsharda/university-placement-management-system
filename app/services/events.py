"""Durable outbox with independent, idempotent notification/reporting consumers."""
import json
from fastapi import APIRouter,Depends,Request
from ..contracts import SimulationSettings
from ..security import current_user,officer,get_record,fail
from ..db import audit,identifier,now

router=APIRouter(prefix='/v1',tags=['Notification and Event Services'])


def process(db):
    result={'events_completed':0,'consumer_effects':0,'failed':0}
    with db.connect(True) as con:
        events=con.execute("SELECT * FROM outbox WHERE status='PENDING' ORDER BY created_at,id LIMIT 100").fetchall()
        outage=con.execute("SELECT value FROM settings WHERE key='notification_outage'").fetchone()[0]=='1'
        for event in events:
            payload=json.loads(event['payload']); error=None
            for consumer in ['reporting','notification']:
                if con.execute('SELECT 1 FROM processed WHERE event_id=? AND consumer=?',(event['id'],consumer)).fetchone(): continue
                if consumer=='notification' and outage:
                    error='Simulated delivery provider outage'; continue
                if consumer=='reporting':
                    if event['event_type'].startswith('Application'):
                        con.execute('INSERT INTO application_projection VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status',
                            (payload['id'],payload['student_id'],payload['drive_id'],payload['status']))
                    elif event['event_type'].startswith('Offer'):
                        con.execute('INSERT INTO offer_projection VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status',
                            (payload['id'],payload['student_id'],payload['drive_id'],payload['status']))
                    con.execute("INSERT INTO settings VALUES('reporting_as_of',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(now(),))
                else:
                    messages={'ApplicationSubmitted':'Your application was submitted successfully.',
                              'ApplicationChanged':'Your application status is now '+payload.get('status','')+'.',
                              'InterviewScheduled':'An interview has been scheduled. Check your interview list.',
                              'InterviewCancelled':'An interview was cancelled. Check your interview list.',
                              'OfferIssued':'You have received an offer. Review its expiry before deciding.',
                              'OfferDecided':'Your offer status is now '+payload.get('status','')+'.'}
                    con.execute('INSERT OR IGNORE INTO notifications VALUES(?,?,?,?,?)',
                        (identifier('N'),event['id'],payload['student_id'],messages.get(event['event_type'],event['event_type']),now()))
                con.execute('INSERT INTO processed VALUES(?,?)',(event['id'],consumer)); result['consumer_effects']+=1
            attempts=event['attempts']+1
            status=('DEAD' if attempts>=3 else 'PENDING') if error else 'DELIVERED'
            con.execute('UPDATE outbox SET status=?,attempts=?,last_error=?,processed_at=? WHERE id=?',
                (status,attempts,error,now() if not error else None,event['id']))
            result['failed' if error else 'events_completed']+=1
    return result


@router.get('/events')
def events(request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect() as con:
        rows=[]
        for row in con.execute('SELECT * FROM outbox ORDER BY created_at DESC,id DESC LIMIT 200'):
            d=dict(row); d['payload']=json.loads(d['payload'])
            d['consumers']=[r[0] for r in con.execute('SELECT consumer FROM processed WHERE event_id=?',(d['id'],))]
            rows.append(d)
        return rows


@router.post('/events/process')
def dispatch(request:Request,user=Depends(current_user)):
    officer(user)
    result=process(request.app.state.db)
    with request.app.state.db.connect(True) as con: audit(con,user['id'],'OutboxProcessed','worker',result)
    return result


@router.post('/events/{event_id}/replay')
def replay(event_id:str,request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect(True) as con:
        get_record(con,'outbox',event_id)
        # Keep consumer receipts: replaying delivered events must not repeat effects.
        con.execute("UPDATE outbox SET status='PENDING',attempts=0,last_error=NULL WHERE id=?",(event_id,))
        audit(con,user['id'],'EventRequeued',event_id,{})
    return {'status':'PENDING'}


@router.get('/notifications')
def notifications(request:Request,user=Depends(current_user)):
    if user['role']=='recruiter': return []
    with request.app.state.db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM notifications WHERE ?='officer' OR student_id=? ORDER BY created_at DESC LIMIT 100",(user['role'],user['student_id']))]


@router.get('/simulation')
def settings(request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect() as con:
        return {'notification_outage':con.execute("SELECT value FROM settings WHERE key='notification_outage'").fetchone()[0]=='1'}


@router.patch('/simulation')
def outage(data:SimulationSettings,request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect(True) as con:
        con.execute("UPDATE settings SET value=? WHERE key='notification_outage'",('1' if data.notification_outage else '0',))
        audit(con,user['id'],'NotificationSimulationChanged','settings',data.model_dump())
    return data.model_dump()


@router.get('/audit')
def history(request:Request,user=Depends(current_user)):
    officer(user)
    with request.app.state.db.connect() as con:
        return [{**dict(r),'detail':json.loads(r['detail'])} for r in con.execute('SELECT * FROM audit ORDER BY created_at DESC LIMIT 200')]
