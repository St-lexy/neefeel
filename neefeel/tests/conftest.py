import sys
from pathlib import Path

# Make `import neefeel` work when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
