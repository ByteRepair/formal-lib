# Author: Yiannis Charalambous

import argparse
import json
import sys
from subprocess import PIPE, STDOUT, run
from time import perf_counter

from formal_lib.issue import VerifierIssue
from formal_lib.issue_parser import IssueRegexSpec, IssueSpecOutputParser
from formal_lib.verifier_output import VerifierOutput
from formal_lib.specs import clang_spec, esbmc_spec, pytest_spec

SPECS: dict[str, IssueRegexSpec] = {
    "esbmc": esbmc_spec,
    "clang": clang_spec,
    "pytest": pytest_spec,
}


def pretty_print(result: VerifierOutput) -> None:
    status = "SUCCESS" if not result.issues else "FAILURE"
    print(f"Verification: {status}")

    if not result.issues:
        print("No issues found.")
        return

    print(f"Issues: {result.issue_count}\n")

    for i, issue in enumerate(result.issues, 1):
        print(f"--- Issue {i} [{issue.severity}] ---")
        print(f"Type: {issue.error_type}")
        if issue.message:
            print(f"Message: {issue.message}")
        if issue.stack_trace:
            print(f"Location: {issue.file_path}:{issue.line_number}")
            if issue.function_name:
                print(f"Function: {issue.function_name}")
        sep = " " if not issue.stack_trace else "\n"
        print(f"Stack trace:{sep}{issue.stack_trace_formatted}")
        if isinstance(issue, VerifierIssue):
            print(f"Counterexample:\n{issue.counterexample_formatted}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="formal-lib",
        description="Parse verifier output into structured JSON. Reads from stdin, or runs a command directly when given after '--'.",
    )

    spec_group = parser.add_mutually_exclusive_group(required=True)
    for name in SPECS:
        spec_group.add_argument(
            f"--{name}",
            dest="spec",
            action="store_const",
            const=name,
            help=f"Parse output as {name}.",
        )

    parser.add_argument(
        "-f",
        "--format",
        choices=["pretty", "json", "json-compact"],
        default="pretty",
        help="Output format (default: pretty).",
    )

    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run (after '--'). Captures exit code and duration.",
    )

    args = parser.parse_args()

    spec = SPECS[args.spec]

    command: list[str] = args.command
    if command and command[0] == "--":
        command = command[1:]

    if command:
        start_time = perf_counter()
        process = run(command, stdout=PIPE, stderr=STDOUT, check=False)
        duration = perf_counter() - start_time
        output = process.stdout.decode("utf-8")
        return_code = process.returncode
    else:
        output = sys.stdin.read()
        return_code = 0
        duration = 0.0

    result = IssueSpecOutputParser(spec).parse_output(
        exit_success=0,
        return_code=return_code,
        duration=duration,
        output=output,
    )

    match args.format:
        case "pretty":
            pretty_print(result)
        case "json":
            print(json.dumps(result.model_dump(mode="json"), indent=2))
        case "json-compact":
            print(json.dumps(result.model_dump(mode="json"), separators=(",", ":")))


if __name__ == "__main__":
    main()
