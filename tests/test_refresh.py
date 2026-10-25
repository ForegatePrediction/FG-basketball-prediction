import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import refresh as r

class RefreshTests(unittest.TestCase):
    def test_missing_data_directory_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'GAMES', tmp):
            league = Path(tmp)/'1'; league.mkdir()
            snap = league/'ratings.json'
            snap.write_text(json.dumps({'mu':100,'hfa':2,'teams':{},'last_date':'2026-04-05'}))
            match = {'date':'2026-04-06','home':'A','away':'B','hp':100,'ap':90,'season':'2026'}
            r._apply('1', {'name':'NBL'}, [match])
            first = snap.read_text()
            self.assertTrue((league/'data/matches.json').exists())
            self.assertEqual(json.loads(first)['last_date'], '2026-04-06')
            r._apply('1', {'name':'NBL'}, [match])
            self.assertEqual(first, snap.read_text())
    def test_gap_is_chunked_without_skipping_history(self):
        dates = r._dates_since('2026-04-05', max_days=31, end_date=dt.date(2026,10,24))
        self.assertEqual((dates[0],dates[-1],len(dates)),('2026-04-06','2026-05-06',31))
        following = r._dates_since('2026-04-05', dates[-1], 31, dt.date(2026,10,24))
        self.assertEqual(following[0], '2026-05-07')
    def test_complete_backfill(self):
        self.assertEqual(len(r._dates_since('2026-04-05', max_days=0, end_date=dt.date(2026,10,24))),202)
    def test_http_failure_is_not_empty_success(self):
        with patch.object(r.urllib.request,'urlopen',side_effect=OSError), patch.object(r.time,'sleep'):
            with self.assertRaises(RuntimeError): r._get('https://example.invalid')
    def test_espn_utc_boundary_and_duplicate_events(self):
        def event(identifier, date):
            return {'id':identifier,'date':date,'status':{'type':{'name':'STATUS_FINAL'}},'competitions':[{'competitors':[{'homeAway':'home','score':'100','team':{'displayName':'A'}},{'homeAway':'away','score':'90','team':{'displayName':'B'}}]}]}
        rows={'events':[event('1','2026-10-24T01:00Z'),event('2','2026-10-25T01:00Z')]}
        with patch.object(r,'_get',return_value=rows) as get:
            matches=r._espn('nba',['2026-10-24'])
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]['date'],'2026-10-24')
        self.assertIn('dates=20261023',get.call_args_list[0].args[0])
    def test_late_same_day_match_is_applied_once(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(r,'GAMES',tmp):
            d=Path(tmp)/'12';d.mkdir()
            (d/'ratings.json').write_text(json.dumps({'teams':{},'last_date':'2026-10-24','applied_on_last_date':['2026-10-24|A|B']}))
            matches=[{'date':'2026-10-24','home':a,'away':b,'hp':100,'ap':90} for a,b in [('A','B'),('C','D')]]
            r._apply('12',{'name':'NBA'},matches)
            snap=json.loads((d/'ratings.json').read_text())
            self.assertNotIn('A',snap['teams'])
            self.assertEqual(snap['teams']['C']['gp'],1)
            self.assertEqual(len(snap['applied_on_last_date']),2)
            r._apply('12',{'name':'NBA'},matches)
            self.assertEqual(json.loads((d/'ratings.json').read_text())['teams']['C']['gp'],1)
    def test_cba_final_regular_games_and_stable_team_ids(self):
        rows=[{'status':4,'matchTypeId':1,'homeTeamId':'29124','visitingTeamId':'29125',
               'scheduleTime':'2026-10-24 19:35:00','homeTeamScore':90,'visitingTeamScore':80,
               'season':2026,'scheduleId':'1'},
              {'status':4,'matchTypeId':3}, {'status':2,'matchTypeId':1}]
        calendar=[{'scheduleTime':'2026-10-24 00:00:00','scheduleNum':3}]
        with patch.object(r,'_cba_list',side_effect=[calendar,rows]):
            matches=r._cba(['2026-10-24'])
        self.assertEqual(len(matches),1)
        self.assertEqual((matches[0]['home'],matches[0]['away']),('Guangdong','Shanghai'))
    def test_cba_missing_daily_results_fails(self):
        calendar=[{'scheduleTime':'2026-10-24 00:00:00','scheduleNum':3}]
        with patch.object(r,'_cba_list',side_effect=[calendar,[]]):
            with self.assertRaises(RuntimeError):r._cba(['2026-10-24'])
    def test_one_failed_source_does_not_block_other_leagues(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); games=root/'games'; games.mkdir()
            for code in ('1','12'):
                d=games/code; d.mkdir(); (d/'ratings.json').write_text('{"last_date":"2026-10-20"}')
            cfgs=[('1',{'name':'NBL','source':'espn','espn_path':'nbl'}),('12',{'name':'NBA','source':'espn','espn_path':'nba'})]
            def fetch(path,*args):
                if path=='nbl': raise RuntimeError('upstream failed')
                return []
            with patch.object(r,'ROOT',tmp),patch.object(r,'GAMES',str(games)),patch.object(r,'_configs',return_value=cfgs),patch.object(r,'_espn',side_effect=fetch),patch.object(sys,'argv',['refresh.py']):
                with self.assertRaises(SystemExit): r.main()
            state=json.loads((root/'refresh-state.json').read_text())
            self.assertNotIn('1',state)
            self.assertIn('12',state)

if __name__=='__main__': unittest.main()
