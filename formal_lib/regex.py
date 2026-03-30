# Author: Yiannis Charalambous

import re

# Regex pattern for stripping ANSI color codes
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
