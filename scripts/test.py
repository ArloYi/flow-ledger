"""Run the shared regression suite without touching real user data."""
import os
from pathlib import Path
import sys
import unittest
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'app/core'))
os.chdir(root/'app/core')
suite=unittest.defaultTestLoader.discover(str(root/'tests'))
sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
