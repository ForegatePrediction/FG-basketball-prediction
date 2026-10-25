import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import storage, predict

ROOT=Path(__file__).resolve().parents[1]


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def generation(self,name,number=1):
        root=self.root/name;root.mkdir()
        (root/'manifest.json').write_text(json.dumps({'schema':1,'engine':storage.ENGINE,'generation':name,
          'channel':'vps','kind':'refresh','created_at':'2026-10-26T00:00:00+00:00','code_revision':'fixture'}))
        return root

    def test_legacy_mode_and_provenance(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(storage.games('/legacy/games'),Path('/legacy/games'))
            self.assertEqual(storage.provenance()['mode'],'repository')

    def test_atomic_pointer_changes_are_visible_without_restarting_predictor(self):
        cfg=next(p for p in (ROOT/'games').glob('*/config.json')
                 if not json.loads(p.read_text()).get('pool_ref') and (p.parent/'ratings.json').exists())
        code=cfg.parent.name
        for n in (1,2):
            root=self.generation(str(n));target=root/'games'/code;target.mkdir(parents=True)
            (target/'ratings.json').write_text(json.dumps({'mu':.2,'hfa':.1,'teams':{'Fixture A':{'rating':1500+n,'gp':n},'Fixture B':{'rating':1400,'gp':n}}}))
        active=self.root/'current';active.symlink_to(self.root/'1')
        with patch.dict(os.environ,{'FG_DATA_DIR':str(active)}):
            old_file=storage.snapshot(ROOT/'games',code)
            first=predict._load(code)[1]
            temp=self.root/'next';temp.symlink_to(self.root/'2');temp.replace(active)
            second=predict._load(code)[1]
            teams1=first if storage.ENGINE=='esports' else first['teams']
            teams2=second if storage.ENGINE=='esports' else second['teams']
            self.assertEqual(teams1['Fixture A']['gp'],1)
            self.assertEqual(teams2['Fixture A']['gp'],2)
            self.assertEqual(json.loads(old_file.read_text())['teams']['Fixture A']['gp'],1)
            self.assertEqual(storage.provenance()['generation'],'2')

    def test_explicit_persistent_data_never_falls_back_to_repository(self):
        with patch.dict(os.environ,{'FG_DATA_DIR':str(self.root/'missing')}):
            with self.assertRaises(FileNotFoundError):storage.games(ROOT/'games')
        root=self.generation('empty')
        with patch.dict(os.environ,{'FG_DATA_DIR':str(root)}):
            with self.assertRaises(FileNotFoundError):storage.snapshot(ROOT/'games','unknown').read_text()

    def test_wrong_engine_data_and_path_traversal_are_rejected(self):
        root=self.generation('wrong');m=json.loads((root/'manifest.json').read_text());m['engine']='another-engine'
        (root/'manifest.json').write_text(json.dumps(m))
        with patch.dict(os.environ,{'FG_DATA_DIR':str(root)}):
            with self.assertRaises(ValueError):storage.games(ROOT/'games')
        with self.assertRaises(ValueError):storage.snapshot(ROOT/'games','../39')


if __name__=='__main__':unittest.main()
