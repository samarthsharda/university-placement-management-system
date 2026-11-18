"""FastAPI gateway composing logical placement services for a local SOA demo."""
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import os
import uuid
from fastapi import Depends,FastAPI,HTTPException,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from .contracts import Login
from .db import Database
from .security import current_user,login,bearer
from .services import profiles,drives,eligibility,applications,scheduling,offers,events,reporting,resumes

ROOT=Path(__file__).resolve().parent
CATALOGUE=[
    ('Profile','profiles.py','Verified academic revisions and private resumes','/v1/students/me'),
    ('Drive Management','drives.py','Draft, approval, publication and closure','/v1/drives'),
    ('Eligibility','eligibility.py','Reusable rules and explainable decisions','/v1/eligibility/evaluations'),
    ('Application','applications.py','Unique submissions, evidence and outbox','/v1/applications'),
    ('Scheduling','scheduling.py','Student, room and interviewer conflict checks','/v1/interviews'),
    ('Offer Management','offers.py','Selection, offer decisions and exclusivity','/v1/offers'),
    ('Notification','events.py','Durable retries, dead letters and deduplication','/v1/events'),
    ('Reporting','reporting.py','Event-driven projection and reconciliation','/v1/reports/placements')]


def create_app(db_path=None):
    db=Database(db_path or os.getenv('PLACEMENT_DB',str(ROOT.parent/'data'/'placement.sqlite3')))

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        yield

    app=FastAPI(title='University Placement Management System',version='1.0.0',lifespan=lifespan,
                description='Academic modular SOA implementation. Fictional records; local demo authentication; no ERP or real email integration.')
    app.state.db=db

    @app.exception_handler(HTTPException)
    async def problem(request,exc):
        return JSONResponse({'type':'about:blank','title':'Request could not be completed','status':exc.status_code,
                             'detail':exc.detail,'instance':request.url.path},status_code=exc.status_code,media_type='application/problem+json')

    @app.exception_handler(RequestValidationError)
    async def invalid(request,exc):
        return JSONResponse({'type':'about:blank','title':'Validation failed','status':422,
            'detail':'; '.join(' / '.join(map(str,e['loc']))+': '+e['msg'] for e in exc.errors()),'instance':request.url.path},status_code=422,media_type='application/problem+json')

    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers['X-Request-ID']=uuid.uuid4().hex
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store' if request.url.path.startswith('/v1') else 'no-cache'
        if request.url.path not in ['/docs','/redoc']:
            response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.get('/health',tags=['Gateway'])
    def health():
        with db.connect() as con: con.execute('SELECT 1')
        return {'status':'ok','application':'university-placement-management','mode':'academic-local-demo','version':'1.0.0'}

    @app.post('/v1/auth/login',tags=['Identity Adapter'])
    def signin(data:Login):
        return login(db,data.email,data.password)

    @app.get('/v1/auth/me',tags=['Identity Adapter'])
    def me(user=Depends(current_user)):
        return user

    @app.post('/v1/auth/logout',tags=['Identity Adapter'])
    def logout(credentials=Depends(bearer),user=Depends(current_user)):
        with db.connect(True) as con:
            con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(credentials.credentials.encode()).hexdigest(),))
        return {'signed_out':True}

    @app.get('/v1/services',tags=['Service Catalogue'])
    def services(user=Depends(current_user)):
        return {'deployment':'Modular SOA: one FastAPI process, one SQLite database, logical service modules; no distributed network transport.',
            'events':'Application transaction -> durable outbox -> independent consumers. Manual dispatch in the service console or python worker.py.',
            'limitations':['Local demo identity instead of OIDC','Academic verification uses officer input instead of ERP','Notifications are an in-app simulated provider, not email','PDF uploads have size/type checks but no antivirus','Pilot load, HA, backup restore and accessibility certification are not claimed'],
            'services':[{'name':name,'module':'app/services/'+module,'capability':cap,'endpoint':endpoint} for name,module,cap,endpoint in CATALOGUE]}

    for module in [profiles,drives,eligibility,applications,scheduling,offers,events,reporting,resumes]:
        app.include_router(module.router)
    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

    @app.get('/',include_in_schema=False)
    def home(): return FileResponse(ROOT/'static'/'index.html')

    return app


app=create_app()
