# Author: Yiannis Charalambous

import argparse
import json
import sys
from subprocess import PIPE, STDOUT, run
from time import perf_counter

from formal_lib.issue import VerifierIssue
from formal_lib.issue_parser import IssueSpecOutputParser
from formal_lib.verifier_output import VerifierOutput
from formal_lib.specs import SPECS, detect_spec


def pretty_print(result: VerifierOutput) -> None:
    status = "SUCCESS" if result.successful else "FAILURE"
    print(f"Verification: {status}")

    if not result.issues:
        print("No issues found.")
        for hint in result.hints:
            print(f"Hint: {hint}")
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
        prog="pf",
        epilog="Made by Yiannis Charalambous (https://yiannis.info) for academia",
        description="Pretty Formal: CLI frontend for the formal-lib library. "
        "Provides a frontend that parses verifier output into structured "
        "different formats. Reads from stdin, or runs a command directly when "
        "given after '--'.",
    )

    parser.add_argument(
        "-b",
        "--backend",
        choices=list(SPECS),
        default=None,
        help="Verifier backend. Auto-detected from output when omitted.",
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

    command: list[str] = args.command
    if command and command[0] == "--":
        command = command[1:]

    if command:
        start_time = perf_counter()
        process = run(command, stdout=PIPE, stderr=STDOUT, check=False)
        duration = perf_counter() - start_time
        output = process.stdout.decode("utf-8")
    elif sys.stdin.isatty():
        parser.error("no input: pipe verifier output or pass a command after '--'")
    else:
        output = sys.stdin.read()
        duration = 0.0

    try:
        spec = SPECS[args.backend] if args.backend else detect_spec(output)
    except ValueError as e:
        parser.error(str(e))

    result = IssueSpecOutputParser(spec).parse_output(
        output=output,
        duration=duration,
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
