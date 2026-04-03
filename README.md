# formal-lib

A Python library that provides structured representations of software verifier
output.

## Backends

The following backends are supported:

- ESBMC
- CBMC
- Clang
- PyTest

## License

> [!NOTE] This project is offered under a [dual-licence](LICENSE) model.

## Frontend

`pf` (Pretty Format) is the frontend for `formal-lib`. It can be invoked from
the CLI to get formatted output from any supported backends. There are two ways
to invoke `pf`:

1. **Preferred:** Using the `--` separator and specifying the command
2. Pipe

### Using the `--` Separator

The `pf` can invoke the command by specifying `--` and the command:

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

Unfortunatley piping as a method of invocation comes with the following
limitations as `pf` only receives textual content from `stdin`:

1. Cannot read the exit code
2. Cannot read duration of execution

These details will be omitted from the output.

## Library Examples

### Formatting ESBMC output

```py
from pathlib import Path
from formal_lib import VerifierRunner, VerifierIssue, esbmc_spec

verifier = VerifierRunner(
    base_cmd=Path("/usr/bin/esbmc"),
    regex_spec=esbmc_spec,
    default_timeout=120,
)

result = verifier.verify_source(Path("main.c"), include_paths=[Path("include/")])

if not result.successful:
    for issue in result.issues:
        print(f"[{issue.severity}] {issue.error_type}: {issue.message}")
        print(f"  Location: {issue.file_path}:{issue.line_number}")
        print(issue.stack_trace_formatted)

        if isinstance(issue, VerifierIssue):
            print(issue.counterexample_formatted)
```

### Running a verifier with auto-detection

```py
from pathlib import Path
from formal_lib import VerifierRunner

verifier = VerifierRunner(base_cmd=Path("/usr/bin/esbmc"), default_timeout=120)
result = verifier.verify_source(Path("main.c"))

for issue in result.issues:
    print(f"[{issue.severity}] {issue.error_type}: {issue.message}")
```

### Analyzing output with auto-detection

```py
from formal_lib import detect_spec, IssueSpecOutputParser

output = open("verifier.log").read()
spec = detect_spec(output)
parser = IssueSpecOutputParser(spec)
result = parser.parse_output(exit_success=0, return_code=1, duration=0, output=output)

for issue in result.issues:
    print(f"[{issue.severity}] {issue.error_type}: {issue.message}")
```

### Filtering traces to specific files

```py
result = verifier.verify_source(Path("main.c"), Path("lib/"))

# Drop traces from system headers or other files not in your project
project_files = {Path("main.c"), Path("lib/utils.c")}
result = result.filter_traces(project_files)
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
