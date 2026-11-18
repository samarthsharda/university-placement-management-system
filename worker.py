"""Run the outbox consumer once, or keep polling in a separate local process."""
import argparse
import time
from app.main import app
from app.services.events import process

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--watch',action='store_true'); args=parser.parse_args()
    app.state.db.initialize()
    while True:
        print(process(app.state.db),flush=True)
        if not args.watch: break
        time.sleep(5)
