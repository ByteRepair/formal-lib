# formal-lib

A Python library that provides structured representations of software verifier
output.

## Backends

The following backends are supported:

- ESBMC (+Fallback to Clang)
- Clang
- PyTest

## License

> [!NOTE]
> This project is offered under a [dual-licence](LICENSE) model.

## CLI Usage

Pipe verifier output to `formal-lib` to parse it into structured output:

```bash
esbmc --k-induction --k-step 2 --max-k-step 10 file.c 2>&1 | formal-lib --esbmc
```

Output formats can be selected with `-f`:

```bash
# Pretty-printed (default)
esbmc file.c 2>&1 | formal-lib --esbmc

# JSON
esbmc file.c 2>&1 | formal-lib --esbmc -f json

# Compact JSON (single line, no whitespace)
esbmc file.c 2>&1 | formal-lib --esbmc -f json-compact
```

Other backends work the same way:

```bash
clang -fsyntax-only file.c 2>&1 | formal-lib --clang
pytest tests/ 2>&1 | formal-lib --pytest
```

## Library Examples

### Formatting ESBMC output

```python
from pathlib import Path
from formal_lib import VerifierRunner
from formal_lib.specs import esbmc_spec
from formal_lib.issue import VerifierIssue

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

### Filtering traces to specific files

```python
result = verifier.verify_source(Path("main.c"), Path("lib/"))

# Drop traces from system headers or other files not in your project
project_files = {Path("main.c"), Path("lib/utils.c")}
result = result.filter_traces(project_files)
```

### Passing ESBMC output to LiteLLM

````python
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
