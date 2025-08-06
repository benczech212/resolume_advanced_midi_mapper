import sys
import os

# Add two folders up to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, parent_dir)
from libraries.resolume_osc_manager import *

# Now you can import modules from two folders up
# Example:
# from some_module import SomeClass

