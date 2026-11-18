"""Read model updated by consumed events, with explicit counting definitions."""
import csv
import io
from fastapi import APIRouter,Depends,Request,Response
from ..security import current_user,officer
from ..db import now

router=APIRouter(prefix='/v1/reports',tags=['Reporting Service'])


def report(db):
    with db.connect() as con:
        cohort=con.execute('SELECT count(*) FROM profiles WHERE graduation_year=2027').fetchone()[0]
        applications=con.execute('SELECT count(*) FROM application_projection a JOIN profiles p ON p.student_id=a.student_id WHERE p.graduation_year=2027').fetchone()[0]
        offers=con.execute('SELECT count(*) FROM offer_projection o JOIN profiles p ON p.student_id=o.student_id WHERE p.graduation_year=2027').fetchone()[0]
        placed=con.execute("SELECT count(DISTINCT o.student_id) FROM offer_projection o JOIN profiles p ON p.student_id=o.student_id WHERE o.status='ACCEPTED' AND p.graduation_year=2027").fetchone()[0]
        accepted=con.execute("SELECT count(*) FROM offer_projection o JOIN profiles p ON p.student_id=o.student_id WHERE o.status='ACCEPTED' AND p.graduation_year=2027").fetchone()[0]
        queued=con.execute("SELECT count(*) FROM outbox WHERE status!='DELIVERED'").fetchone()[0]
        checkpoint=con.execute("SELECT value FROM settings WHERE key='reporting_as_of'").fetchone()
        as_of=checkpoint[0] if checkpoint else None
        missing=con.execute("SELECT count(*) FROM outbox o WHERE NOT EXISTS(SELECT 1 FROM processed p WHERE p.event_id=o.id AND p.consumer='reporting')").fetchone()[0]
        by_programme=[dict(r) for r in con.execute("SELECT p.programme,count(*) AS cohort,count(DISTINCT CASE WHEN o.status='ACCEPTED' THEN p.student_id END) AS placed FROM profiles p LEFT JOIN offer_projection o ON o.student_id=p.student_id WHERE p.graduation_year=2027 GROUP BY p.programme ORDER BY p.programme")]
        source_apps=con.execute('SELECT count(*) FROM applications a JOIN profiles p ON p.student_id=a.student_id WHERE p.graduation_year=2027').fetchone()[0]
        source_offers=con.execute('SELECT count(*) FROM offers o JOIN profiles p ON p.student_id=o.student_id WHERE p.graduation_year=2027').fetchone()[0]
        mismatch=con.execute("SELECT count(*) FROM offers o LEFT JOIN offer_projection p ON p.id=o.id WHERE p.id IS NULL OR p.status!=o.status").fetchone()[0]
        app_mismatch=con.execute("SELECT count(*) FROM applications a LEFT JOIN application_projection p ON p.id=a.id WHERE p.id IS NULL OR p.status!=a.status").fetchone()[0]
        source_placed=con.execute("SELECT count(DISTINCT o.student_id) FROM offers o JOIN profiles p ON p.student_id=o.student_id WHERE o.status='ACCEPTED' AND p.graduation_year=2027").fetchone()[0]
        return {'cohort':cohort,'applications':applications,'offers':offers,'placed':placed,
                'acceptance_rate':round(accepted/offers*100,1) if offers else 0,
                'placement_rate':round(placed/cohort*100,1) if cohort else 0,
                'by_programme':by_programme,'queued_events':queued,'reporting_lag':missing,
                'as_of':as_of,'generated_at':now(),'scope':'All demo drives; 2027 graduating cohort; current retained records',
                'definitions':{'placed':'Distinct 2027 students with an ACCEPTED offer','acceptance_rate':'Currently accepted offers / issued offer records for the 2027 cohort × 100','placement_rate':'Distinct accepted 2027 students / current 2027 cohort × 100'},
                'reconciliation':{'source_applications':source_apps,'source_offers':source_offers,'source_placed':source_placed,
                                  'offer_mismatches':mismatch,'application_mismatches':app_mismatch,
                                  'matched':source_apps==applications and source_offers==offers and not mismatch and not app_mismatch}}


@router.get('/placements')
def summary(request:Request,user=Depends(current_user)):
    officer(user)
    return report(request.app.state.db)


@router.get('/placements.csv')
def export(request:Request,user=Depends(current_user)):
    officer(user)
    data=report(request.app.state.db); stream=io.StringIO(newline=''); writer=csv.writer(stream)
    writer.writerow(['University Placement Management System','Fictional local demo data'])
    for k in ['scope','generated_at','as_of','cohort','applications','offers','placed','acceptance_rate','placement_rate','reporting_lag']:
        writer.writerow([k,data[k]])
    writer.writerow(['programme','cohort','placed'])
    for row in data['by_programme']: writer.writerow([row['programme'],row['cohort'],row['placed']])
    for key,value in data['definitions'].items(): writer.writerow([key+' definition',value])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="placement-report.csv"'})
