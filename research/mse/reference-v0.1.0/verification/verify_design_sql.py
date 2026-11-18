#!/usr/bin/env python3
"""Verify the new-database proposal in memory only; never accepts a DB path."""
from pathlib import Path
import json
import sqlite3

root=Path(__file__).resolve().parents[1]
db=sqlite3.connect(':memory:')
db.executescript((root/'design/001_mse_proposed.sql').read_text())
checks=[]
def expect_failure(label, sql, values):
    try:
        db.execute(sql,values)
    except sqlite3.IntegrityError:
        checks.append({'name':label,'passed':True})
    else:
        raise AssertionError(label)

tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
assert set(tables)=={'model_versions','mechanism_bundles','evidence_snapshots','snapshot_inputs',
                    'inference_runs','feature_values','state_estimates','state_validity_events',
                    'hypothesis_sets','measurement_requests'}
checks.append({'name':'10 proposed tables and current-state view created','passed':True})
expect_failure('strict availability requires cutoff',
 'INSERT INTO evidence_snapshots VALUES(?,?,?,?,?,?,?)',
 ('s','a'*64,'1','{}','strict_authoritative_availability',None,'2026-01-01T00:00:00Z'))
db.execute('INSERT INTO evidence_snapshots VALUES(?,?,?,?,?,?,?)',
 ('s','a'*64,'1','{}','retrospective',None,'2026-01-01T00:00:00Z'))
db.execute('INSERT INTO model_versions VALUES(?,?,?,?,?,?,?)',
 ('m','v','b'*64,'c'*64,'{}','{}','2026-01-01T00:00:00Z'))
db.execute('INSERT INTO inference_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
 ('r','m','v','s',None,None,'retrospective','{}',None,'2026-01-01T00:00:00Z',None,'running',None))
state_sql='INSERT INTO state_estimates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
state=('state1','r','synthetic','heart-rate-residual','v1','2026-01-01T00:00:00Z',None,
       'unknown',None,'insufficient_coverage','unvalidated','{}','{}','[]')
bad=list(state);bad[9]=None
expect_failure('unknown state requires reason',state_sql,bad)
bad=list(state);bad[8]='{}'
expect_failure('unknown state cannot carry numeric posterior',state_sql,bad)
bad=list(state);bad[1]='missing-run'
expect_failure('state requires existing model run',state_sql,bad)
db.execute(state_sql,state)
assert db.execute('SELECT COUNT(*) FROM current_valid_state_estimates').fetchone()[0]==1
db.execute('INSERT INTO state_validity_events(event_id,estimate_id,validity,reason,recorded_at) VALUES(?,?,?,?,?)',
           ('v1','state1','source_revised','Synthetic source correction','2026-01-02T00:00:00Z'))
assert db.execute('SELECT COUNT(*) FROM current_valid_state_estimates').fetchone()[0]==0
assert db.execute('SELECT COUNT(*) FROM state_estimates').fetchone()[0]==1
checks.append({'name':'source correction excludes current view while retaining history','passed':True})
db.execute('INSERT INTO hypothesis_sets VALUES(?,?,?,?,?,?,?)',
           ('h','state1',None,'[]',1,0,'2026-01-01T00:00:00Z'))
expect_failure('measurement request grants no execution authority',
               'INSERT INTO measurement_requests VALUES(?,?,?,?,?,?)',
               ('q','h','0.1.0','{}','autonomous','2026-01-01T00:00:00Z'))
db.close()
result={'schema':'MSE-001-proposed-sql','checks':checks,'passed':len(checks),
        'failed':0,'scope':'in-memory SQL software invariants only; no biology or production migration'}
print(json.dumps(result,indent=2))
