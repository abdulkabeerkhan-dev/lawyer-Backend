import unittest
import os
import sys
import time
from fastapi import HTTPException
from fastapi.testclient import TestClient

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

import main
from main import app, check_burst_rate_limit, _BURST_RATE_LIMIT_STORE, _BURST_RATE_LIMIT_LOCK

class TestBurstRateLimitAndLegalPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        with _BURST_RATE_LIMIT_LOCK:
            _BURST_RATE_LIMIT_STORE.clear()

    def test_burst_rate_limit_allows_under_threshold(self):
        uid = 'user_burst_test_1'
        for _ in range(5):
            check_burst_rate_limit(uid, action='test_action')

    def test_burst_rate_limit_blocks_exceeding_threshold(self):
        uid = 'user_burst_test_2'
        for _ in range(5):
            check_burst_rate_limit(uid, action='test_action')
        
        with self.assertRaises(HTTPException) as ctx:
            check_burst_rate_limit(uid, action='test_action')
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn('Retry-After', ctx.exception.headers)
        self.assertIn('Burst rate limit exceeded', ctx.exception.detail)

    def test_burst_rate_limit_mock_user_exempt(self):
        uid = 'mock_clerk_user_id_dev_run'
        for _ in range(15):
            check_burst_rate_limit(uid, action='test_action')

    def test_disclaimer_endpoint_public(self):
        res = self.client.get('/disclaimer')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('independent_verification_requirement', data)
        self.assertIn('PLD', data['independent_verification_requirement'])
        self.assertIn('SCMR', data['independent_verification_requirement'])

    def test_privacy_endpoint_public_and_truthful(self):
        res = self.client.get('/privacy')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        flows = data.get('subprocessors_and_data_flows', {})
        self.assertIn('searxng_and_upstream_search', flows)
        self.assertIn('leave private infrastructure', flows['searxng_and_upstream_search'])
        self.assertIn('anthropic', flows)
        self.assertIn('Zero Data Retention is subject to verified enterprise agreement', flows['anthropic'])

    def test_terms_endpoint_public(self):
        res = self.client.get('/terms')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('independent_verification_duty', data)
        self.assertIn('abuse_restrictions', data)
        self.assertIn('limitation_of_liability', data)

if __name__ == '__main__':
    unittest.main()
