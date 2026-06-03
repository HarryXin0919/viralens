"""Let pytest import the flat scripts/ modules without installing the package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
