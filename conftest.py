"""Make the project root importable so tests can `import timebutler_run`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
