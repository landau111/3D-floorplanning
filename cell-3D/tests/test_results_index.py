"""Verify preservation and formal/quick latest-result selection."""
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from results_index import allocate_output,update_index

class ResultsTests(unittest.TestCase):
    def test_collision_and_preserve(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root=Path(temporary)
            now=datetime.datetime(2026,10,13,22,30)
            first=allocate_output(root,now=now);first.mkdir(parents=True)
            second=allocate_output(root,now=now)
            self.assertEqual(second.name,"223000_layout_02")
            (first/"original").write_text("keep")
            with self.assertRaises(ValueError):allocate_output(root,first)
            self.assertEqual((first/"original").read_text(),"keep")

    def test_quick_failure_do_not_replace_formal(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root=Path(temporary)
            for name,kind,status in [("010000_layout","formal","complete"),("020000_layout","quick","complete"),("030000_layout","formal","running")]:
                folder=root/"2026-10-13"/name;folder.mkdir(parents=True)
                (folder/"run_info.json").write_text(json.dumps(dict(kind=kind,status=status,started_at=name)))
                (folder/"manifest.json").write_text('{"no_feasible_candidate":true}')
            latest=update_index(root)
            self.assertEqual(latest["run"],"010000_layout")
            self.assertEqual(len(json.loads((root/"catalog.json").read_text())),3)
            self.assertIn("无布线可行",(root/"LATEST.md").read_text(encoding="utf-8"))

if __name__=="__main__":unittest.main()
