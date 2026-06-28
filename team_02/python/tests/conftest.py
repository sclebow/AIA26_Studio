"""Put team_02/python on sys.path so tests can import spatial / nodes / comfort directly."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
