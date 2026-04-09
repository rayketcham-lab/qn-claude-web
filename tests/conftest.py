"""Shared test fixtures for QN Code Assistant"""
import json
import os
import sys
import tempfile

# Add vendor and project to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_vendor_dir = os.path.join(_project_root, 'vendor')
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import unittest


def get_test_app():
    """Create a test Flask app with testing config"""
    import app as app_module
    app_module.app.config['TESTING'] = True
    app_module.app.config['SECRET_KEY'] = 'test-secret-key'
    return app_module.app, app_module
