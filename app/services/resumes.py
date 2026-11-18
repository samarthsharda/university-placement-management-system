"""Private, size-limited PDF storage. Antivirus scanning is outside this demo."""
from pathlib import Path
import re
from fastapi import APIRouter,Depends,Request
from fastapi.responses import FileResponse
from ..security import current_user,fail,get_record
from ..db import audit,identifier,now

router=APIRouter(prefix='/v1/resumes',tags=['Profile Service'])


@router.get('')
def listing(request:Request,user=Depends(current_user)):
    if user['role']!='student': fail(403,'Student access required')
    with request.app.state.db.connect() as con:
        return [{k:r[k] for k in ['id','name','created_at']} for r in con.execute('SELECT * FROM resumes WHERE student_id=? ORDER BY created_at DESC',(user['student_id'],))]


@router.post('',status_code=201)
async def upload(request:Request,name:str='resume.pdf',user=Depends(current_user)):
    if user['role']!='student': fail(403,'Student access required')
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>2*1024*1024: fail(413,'Resume must be at most 2 MB')
    if not content.startswith(b'%PDF-'): fail(400,'Upload a PDF file')
    rid=identifier('RV'); filename=rid+'.pdf'
    clean=re.sub(r'[^a-zA-Z0-9_. -]','_',name.replace('\\','/').split('/')[-1])[:100] or 'resume.pdf'
    path=request.app.state.db.uploads/filename
    path.write_bytes(content)
    try:
        with request.app.state.db.connect(True) as con:
            con.execute('INSERT INTO resumes VALUES(?,?,?,?,?)',(rid,user['student_id'],clean,filename,now()))
            audit(con,user['id'],'ResumeUploaded',rid,{'size':len(content)})
    except Exception:
        path.unlink(missing_ok=True); raise
    return {'id':rid,'name':clean}


@router.get('/{resume_id}')
def download(resume_id:str,request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        resume=get_record(con,'resumes',resume_id)
        allowed=user['role']=='officer' or (user['role']=='student' and user['student_id']==resume['student_id'])
        if user['role']=='recruiter':
            allowed=bool(con.execute('SELECT 1 FROM applications a JOIN drives d ON d.id=a.drive_id WHERE a.resume_version=? AND d.company_id=?',(resume_id,user['company_id'])).fetchone())
        if not allowed: fail(403,'You do not have access to this resume')
    return FileResponse(request.app.state.db.uploads/resume['filename'],media_type='application/pdf',filename=resume['name'])
