"""Pytest configuration. Adds the gui/ directory to sys.path so tests can
import the analytics modules without a setup.py."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_GUI = os.path.join(os.path.dirname(_HERE), 'gui')
if _GUI not in sys.path:
    sys.path.insert(0, _GUI)
