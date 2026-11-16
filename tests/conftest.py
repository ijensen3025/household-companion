"""Offline test shim: Firestore is installed in Cloud Run, not this test container."""
import sys
import types
try:
    from google.cloud import firestore  # noqa: F401
except ImportError:
    module = types.ModuleType("google.cloud.firestore")
    module.transactional = lambda f: f
    sys.modules["google.cloud.firestore"] = module
