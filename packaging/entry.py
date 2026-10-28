import os
import sys

from localphraser.main import main

# Windowed Windows executables have no Python standard streams. Libraries such as
# tqdm require a writable stream even though this application keeps no log files.
for name, mode in (("stdout", "w"), ("stderr", "w"), ("stdin", "r")):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, mode, encoding="utf-8"))

raise SystemExit(main())
