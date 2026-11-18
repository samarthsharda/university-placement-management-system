"""Reusable deterministic eligibility contract, also called during submission."""
import json
from fastapi import APIRouter,Depends,Request
from ..contracts import EvaluationRequest
from ..security import current_user,drive_access,get_record,fail
from ..db import now
from .profiles import profile

router=APIRouter(prefix='/v1/eligibility',tags=['Eligibility Service'])


def evaluate(con,student_id,drive):
    student=profile(con,student_id)
    reasons=[]
    if drive['status']!='PUBLISHED' or drive['deadline']<=now(): reasons.append('DRIVE_CLOSED')
    if not student['verified']:
        status='REVIEW_REQUIRED'; reasons.append('ACADEMIC_UNVERIFIED')
    else:
        if student['programme'] not in json.loads(drive['programmes']): reasons.append('PROGRAMME_NOT_ALLOWED')
        if student['graduation_year']!=drive['graduation_year']: reasons.append('YEAR_MISMATCH')
        if student['cgpa_hundredths']<drive['minimum_cgpa']: reasons.append('CGPA_BELOW_MINIMUM')
        if student['backlogs']>drive['maximum_backlogs']: reasons.append('BACKLOG_LIMIT_EXCEEDED')
        status='ELIGIBLE' if not reasons else 'INELIGIBLE'
    if con.execute("SELECT 1 FROM offers WHERE student_id=? AND status='ACCEPTED'",(student_id,)).fetchone():
        reasons.append('ACCEPTED_OFFER_POLICY'); status='INELIGIBLE'
    return {'decision':status,'reasons':reasons,'student_id':student_id,'drive_id':drive['id'],
            'academic_version':student['version'],'policy_version':drive['policy_version'],
            'evaluated_at':now(),'academic_snapshot':student,
            'policy_snapshot':{k:drive[k] for k in ['programmes','graduation_year','minimum_cgpa','maximum_backlogs','deadline']}}


@router.post('/evaluations')
def evaluation(data:EvaluationRequest,request:Request,user=Depends(current_user)):
    with request.app.state.db.connect() as con:
        drive=get_record(con,'drives',data.drive_id)
        sid=data.student_id or user['student_id']
        if not sid: fail(400,'Choose a student')
        if user['role']=='student':
            if sid!=user['student_id']: fail(403,'Only your own eligibility is available')
            if drive['status']=='DRAFT': fail(404,'Drive not found')
        else:
            drive_access(user,drive)
            if user['role']=='recruiter': fail(403,'Only officers can preview another student before application')
        return evaluate(con,sid,drive)
