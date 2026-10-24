# -*- coding: utf-8 -*-
import app as app_module


def test_health():
    client = app_module.app.test_client()
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'service': 'xide'}
