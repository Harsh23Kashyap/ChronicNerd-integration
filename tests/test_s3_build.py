"""The S3 artifact must never ship a localhost or plaintext API endpoint."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'build-s3-site.sh'

class S3BuildTest(unittest.TestCase):
    def test_build_sets_same_origin_api_and_preserves_site(self):
        with tempfile.TemporaryDirectory() as output:
            env = dict(os.environ, API_URL='/api')
            subprocess.run([str(SCRIPT), output], env=env, check=True, capture_output=True)
            artifact = pathlib.Path(output)
            self.assertIn("API_URL: '/api'", (artifact/'env.js').read_text())
            self.assertNotIn('localhost', (artifact/'env.js').read_text())
            self.assertTrue((artifact/'index.html').is_file())
            self.assertTrue((artifact/'api.js').is_file())

    def test_build_rejects_plain_http(self):
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run([str(SCRIPT), output], env=dict(os.environ, API_URL='http://example.org'), capture_output=True)
            self.assertNotEqual(result.returncode, 0)
