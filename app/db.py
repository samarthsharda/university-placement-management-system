"""SQLite unit of work. Immediate writes serialize conflicting decisions."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import os
import secrets
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(prefix):
    return prefix + uuid.uuid4().hex[:12].upper()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()
    return salt + ':' + digest


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads = self.path.parent / 'resumes'
        self.uploads.mkdir(exist_ok=True)

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=15000')
        try:
            if write:
                con.execute('BEGIN IMMEDIATE')
            yield con
            if write:
                con.commit()
        except Exception:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        with self.connect() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript(SCHEMA)
        with self.connect(True) as con:
            if con.execute('SELECT count(*) FROM users').fetchone()[0]:
                return
            hashed = password_hash('Placement@123')
            users = [('O01','officer@demo.edu','Dr. Kavya Rao','officer',None,None),
                     ('R01','recruiter@demo.edu','Anita Mehta','recruiter','C01',None),
                     ('R02','recruiter2@demo.edu','Rohan Kapoor','recruiter','C02',None)]
            names = ['Aarav Sharma','Diya Nair','Ishaan Verma','Meera Iyer','Riya Shah','Vihaan Rao']
            programmes = ['CSE','IT','CSE','ECE','IT','CSE']
            cgpas = [820,700,680,810,760,800]
            for i, name in enumerate(names, 1):
                sid = f'S{i:02}'
                users.append((sid,f's{i:02}@demo.edu',name,'student',None,sid))
                con.execute('INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (sid,name,f's{i:02}@demo.edu',programmes[i-1],2027,cgpas[i-1],int(i==5),int(i!=6),1,now()))
            con.executemany('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
                            [(*u,hashed) for u in users])
            deadline = (datetime.now(timezone.utc)+timedelta(days=90)).isoformat()
            for values in [('D101','Graduate Software Engineer','Northstar Technologies','C01','PUBLISHED',700),
                           ('D102','Platform Engineer','Vertex Labs','C02','DRAFT',750)]:
                did,title,company,cid,status,minimum = values
                con.execute('INSERT INTO drives VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (did,title,company,cid,status,json.dumps(['CSE','IT']),2027,minimum,0,deadline,1,'Chennai · On campus',now()))
            con.executemany('INSERT INTO settings VALUES(?,?)', [('notification_outage','0'),('one_offer_policy','1')])


def audit(con, actor, action, entity, detail):
    con.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',
                (identifier('AU'),actor,action,entity,json.dumps(detail),now()))


def emit(con, event_type, payload):
    eid = identifier('EV')
    con.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',
                (eid,event_type,json.dumps(payload),now(),'PENDING',0,None,None))
    return eid


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT,role TEXT,company_id TEXT,student_id TEXT,password TEXT);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires_at TEXT);
CREATE TABLE IF NOT EXISTS profiles(student_id TEXT PRIMARY KEY,name TEXT,email TEXT,programme TEXT,graduation_year INTEGER,cgpa_hundredths INTEGER,backlogs INTEGER,verified INTEGER,version INTEGER,updated_at TEXT);
CREATE TABLE IF NOT EXISTS resumes(id TEXT PRIMARY KEY,student_id TEXT,name TEXT,filename TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS drives(id TEXT PRIMARY KEY,title TEXT,company TEXT,company_id TEXT,status TEXT,programmes TEXT,graduation_year INTEGER,minimum_cgpa INTEGER,maximum_backlogs INTEGER,deadline TEXT,policy_version INTEGER,location TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY,student_id TEXT,drive_id TEXT REFERENCES drives(id),status TEXT,snapshot TEXT,resume_version TEXT,created_at TEXT,version INTEGER,UNIQUE(student_id,drive_id));
CREATE TABLE IF NOT EXISTS idempotency(principal TEXT,key TEXT,drive_id TEXT,digest TEXT,application_id TEXT,PRIMARY KEY(principal,key));
CREATE TABLE IF NOT EXISTS interviews(id TEXT PRIMARY KEY,application_id TEXT REFERENCES applications(id),student_id TEXT,drive_id TEXT,interviewer TEXT,room TEXT,start TEXT,end TEXT,status TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,application_id TEXT UNIQUE REFERENCES applications(id),student_id TEXT,drive_id TEXT,title TEXT,status TEXT,expires_at TEXT,created_at TEXT,version INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS one_accepted_offer ON offers(student_id) WHERE status='ACCEPTED';
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,event_type TEXT,payload TEXT,created_at TEXT,status TEXT,attempts INTEGER,last_error TEXT,processed_at TEXT);
CREATE TABLE IF NOT EXISTS processed(event_id TEXT,consumer TEXT,PRIMARY KEY(event_id,consumer));
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,event_id TEXT UNIQUE,student_id TEXT,message TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS application_projection(id TEXT PRIMARY KEY,student_id TEXT,drive_id TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS offer_projection(id TEXT PRIMARY KEY,student_id TEXT,drive_id TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,actor TEXT,action TEXT,entity TEXT,detail TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
'''
