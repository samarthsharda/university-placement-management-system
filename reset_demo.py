"""Archive local demo data and start a fresh cohort; never delete user data silently."""
from datetime import datetime
from pathlib import Path
import argparse

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Stop the server and worker before resetting.')
    parser.add_argument('--confirm',action='store_true',help='Archive current local data and seed a fresh database on next start')
    args=parser.parse_args()
    if not args.confirm: parser.error('Stop the server and worker, then pass --confirm to archive demo data.')
    root=Path(__file__).resolve().parent; data=root/'data'
    if data.exists():
        target=root/('data-archive-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        data.rename(target); print('Previous demo data archived at',target)
    print('A fresh six-student cohort will be created on the next server start.')
