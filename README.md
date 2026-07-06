# `formal-lib`

[![CI](https://github.com/ByteRepair/formal-lib/actions/workflows/ci.yml/badge.svg)](https://github.com/ByteRepair/formal-lib/actions/workflows/ci.yml)

A Python library that provides structured representations of software verifier
output.

## Installation

- [PyPI](https://pypi.org/project/formal-lib/) _(Recommended)_
- [GitHub Releases](https://github.com/ByteRepair/formal-lib/releases/latest)

## Backends

The following backends are supported:

- ESBMC
- CBMC
- Clang
- PyTest

## Frontend

`pf` (Pretty Format) is a CLI frontend for `formal-lib`. It can be invoked from
the CLI to get formatted output from any supported backends. There are two ways
to invoke `pf`; detailed below.

### Using the `--` Separator (Recommeded)

The verifier command is specified after the `--` separator. Any builtin backend
can be specified. For example:

```bash
pf -- esbmc --k-induction --k-step 2 --max-k-step 10 file.c
```

This makes it easier for some backends that use `stderr` like ESBMC as you don't
need to redirect `stderr` to `stdout` before piping.

### Pipe

Pipe verifier output to `pf` to parse it into structured output:

```bash
esbmc --k-induction --k-step 2 --max-k-step 10 file.c 2>&1 | pf
```

Piping as a method of invocation cannot measure the duration of execution, so
that detail will be omitted from the output.

## Library Examples

The following section shows some simple examples of the capability of
`formal-lib`.

### Running a Verifier

```py
from pathlib import Path
from formal_lib import VerifierRunner

verifier = VerifierRunner(base_cmd=Path("/usr/bin/esbmc"), default_timeout=120)
result = verifier.verify_source(Path("main.c"))

for issue in result.issues:
    print(f"[{issue.severity}] {issue.error_type}: {issue.message}")
```

### Analyzing Verifier Output

```py
from formal_lib import detect_spec, IssueSpecOutputParser

output = open("verifier.log").read()
spec = detect_spec(output)
parser = IssueSpecOutputParser(spec)
result = parser.parse_output(output=output)

# Drop traces from system headers or other files not in your project
project_files = {Path("main.c"), Path("lib/utils.c")}
result = result.filter_traces(project_files)

for issue in result.issues:
    print(f"[{issue.severity}] {issue.error_type}: {issue.message}")
```

### Passing ESBMC output to LiteLLM

````py
from pathlib import Path
import litellm
from formal_lib import VerifierRunner
from formal_lib.specs import esbmc_spec
from formal_lib.issue import VerifierIssue

verifier = VerifierRunner(base_cmd=Path("/usr/bin/esbmc"), regex_spec=esbmc_spec)
result = verifier.verify_source(Path("main.c"))

if not result.successful:
    issue = result.primary_issue
    counterexample = ""
    if isinstance(issue, VerifierIssue):
        counterexample = f"\nCounterexample:\n{issue.counterexample_formatted}"

    source = Path("main.c").read_text()

    response = litellm.completion(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Fix the following {issue.error_type} in {issue.file_path}:{issue.line_number}:\n"
                    f"{issue.message}\n\n"
                    f"Stack trace:\n{issue.stack_trace_formatted}"
                    f"{counterexample}\n\n"
                    f"Source:\n```c\n{source}\n```"
                ),
            }
        ],
    )
    print(response.choices[0].message.content)
````

## License

Copyright © 2026 The University of Manchester. Authored by Yiannis Charalambous.

> [!NOTE] This project is offered under a [dual-licence](LICENSE) model: the
> open-source **GNU AGPL-3.0**, or a separate **commercial licence** for
> proprietary use.

For a commercial licence, contact UOM Innovation Factory (the commercialisation
subsidiary of The University of Manchester) at contact@uominnovationfactory.com.
