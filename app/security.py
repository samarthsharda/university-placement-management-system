"""Local demonstration identity, not institutional OIDC."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .db import now, password_hash, audit

bearer = HTTPBearer(auto_error=False)


def fail(status, message):
    raise HTTPException(status_code=status, detail=message)


def login(db, email, password):
    with db.connect(True) as con:
        row = con.execute('SELECT * FROM users WHERE email=?',(email.lower(),)).fetchone()
        if not row or not secrets.compare_digest(password_hash(password, row['password'].split(':')[0]),row['password']):
            fail(401,'Incorrect email or password')
        token = secrets.token_urlsafe(40)
        con.execute('DELETE FROM sessions WHERE expires_at < ?',(now(),))
        con.execute('INSERT INTO sessions VALUES(?,?,?)',
            (hashlib.sha256(token.encode()).hexdigest(),row['id'],(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
        audit(con,row['id'],'SignedIn',row['id'],{})
        return {'token':token,'user':public_user(row)}


def public_user(row):
    return {k:row[k] for k in ('id','email','name','role','company_id','student_id')}


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials:
        fail(401,'Please sign in')
    with request.app.state.db.connect() as con:
        row = con.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',
            (hashlib.sha256(credentials.credentials.encode()).hexdigest(),now())).fetchone()
    if not row:
        fail(401,'Your session has expired. Please sign in again')
    return public_user(row)


def staff(user):
    if user['role'] not in ('officer','recruiter'):
        fail(403,'Placement staff access required')


def officer(user):
    if user['role']!='officer':
        fail(403,'Placement officer access required')


def drive_access(user, drive):
    staff(user)
    if user['role']=='recruiter' and user['company_id']!=drive['company_id']:
        fail(403,'This drive belongs to another company')


def get_record(con, table, record_id):
    # Table names are fixed by callers, never accepted from HTTP input.
    row = con.execute(f'SELECT * FROM {table} WHERE id=?',(record_id,)).fetchone()
    if not row:
        fail(404,'Record not found')
    return row
