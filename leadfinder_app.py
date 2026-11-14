"""Owner Lead Finder — entry point for the str-lead-finder Render service.

The unified app (app.py) is one deploy; this file is a thin shim so the
existing service (`streamlit run leadfinder_app.py`) boots the same app with
the leads lane preselected via LANDING_MODE=leads.
"""

import os
from pathlib import Path
import runpy

os.environ.setdefault("LANDING_MODE", "leads")
runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
