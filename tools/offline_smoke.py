"""Run a fresh synthetic campaign with network access blocked in-process."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_lab.meno2_campaign import create_campaign, run_campaign, export_campaign
from research_lab.storage import read_json


def main():
    with tempfile.TemporaryDirectory(prefix='meno-offline-') as tmp:
        campaign = Path(tmp)/'campaign'
        exported = Path(tmp)/'replay'
        with patch('socket.socket.connect', side_effect=AssertionError('Network disabled')):
            create_campaign(campaign, read_json(ROOT/'examples'/'offline-demo.json'))
            report = run_campaign(campaign)
            assert report['status']['evidence_kind'] == 'synthetic'
            assert report['status']['completed_trials'] == 9
            export_campaign(campaign, exported)
        replay = subprocess.run([sys.executable, '-B', str(exported/'reproduce.py')],
                                capture_output=True, text=True)
        if replay.returncode:
            raise SystemExit(replay.stderr)
        print(json.dumps({'evidence_kind': 'synthetic', 'completed_trials': 9,
                          'observed_cost_usd': report['status']['observed_cost_usd'],
                          'generation_network_blocked': True,
                          'fresh_demo_replay': replay.stdout.strip(),
                          'historical_raw_response_replay': False}, indent=2))


if __name__ == '__main__':
    main()

