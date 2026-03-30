# Author: Yiannis Charalambous

"""This module holds the code for the verifier runner."""

import os
from pathlib import Path
from time import perf_counter
from subprocess import PIPE, STDOUT, run, CompletedProcess
from typing import Any, cast
from hashlib import sha256
import pickle
import zlib

from platformdirs import user_cache_dir
from pydantic import BaseModel, DirectoryPath, FilePath, Field

from formal_lib.verifier_output import VerifierOutput
from formal_lib.issue_parser import IssueRegexSpec, IssueSpecOutputParser
from formal_lib import __version__, logger

_PROCESS_TIMEOUT_SLACK_SECONDS: int = 5


class SourceCodeParseError(Exception):
    """Error that means that SolutionGenerator could not parse the source code
    to return the right format."""


class VerifierTimedOutException(Exception):
    """Error that means that the verifier timed out and so the error could not be
    determined."""


class VerifierRunner(BaseModel):
    """Runs an external verifier command and parses its output."""

    base_cmd: FilePath = Field()
    """Path to the binary"""
    exit_success: int = Field(default=0)
    """Return code that indicates successful verification."""
    default_timeout: int | None = Field(default=None)
    """Default timeout in seconds. Used when verify_source is called without
    an explicit timeout."""
    enable_cache: bool = Field(default=False)
    """Whether to enable result caching."""
    regex_spec: IssueRegexSpec = Field()
    """Regex specification for parsing verifier output. If None, inferred from
    source file extensions."""

    def _cache_name_pack(self, properties: Any) -> Any:
        """Packs additional version properties to the cache name in order to ensure
        it only functions in the current version of this package."""
        return [__version__, properties]

    def _compute_cache_id(self, properties: Any) -> str:
        """Compute a stable cache ID from properties using content-based hashing.

        Uses __hash__ methods of objects (e.g., Solution, SourceFile) to create
        stable, content-based cache keys that work across different file paths
        and Python processes.

        Uses zlib.adler32 for deterministic hashing of collections instead of
        Python's hash() which is randomized across processes.
        """
        properties = self._cache_name_pack(properties)

        def deterministic_hash(obj: Any) -> int:
            """Compute deterministic hash using adler32 and custom __hash__ methods.

            For objects with custom __hash__ (like Solution), uses their hash.
            For collections and primitives, uses adler32 for deterministic hashing.
            """
            if isinstance(obj, (list, tuple)):
                # Recursively hash elements and combine
                element_hashes = [str(deterministic_hash(item)) for item in obj]
                combined = "|".join(element_hashes)
                return zlib.adler32(combined.encode("utf-8"))
            elif isinstance(obj, (str, int, float, bool, type(None))):
                # Primitives: use adler32 for deterministic hashing
                # (Python's hash() for str is randomized!)
                return zlib.adler32(str(obj).encode("utf-8"))
            elif hasattr(obj, "__hash__") and type(obj).__hash__ is not object.__hash__:
                # Object has custom __hash__ method (e.g., Solution, SourceFile)
                # These are already content-based and deterministic (SHA256-based)
                return hash(obj)
            else:
                # Fallback: use adler32 of string representation
                return zlib.adler32(str(obj).encode("utf-8"))

        cache_hash = deterministic_hash(properties)
        return sha256(str(cache_hash).encode("utf-8")).hexdigest()

    def _save_cached(self, properties: Any, result: Any) -> None:
        """Saves the verification results to a cached directory to be loaded
        later. Properties are going to be hashed to form the name of the file,
        they should be anything that defines the file."""
        file_id: str = self._compute_cache_id(properties)
        logger.info("Saving result to cache")
        logger.info(f"Cache ID: {file_id}")

        cache: Path = Path(user_cache_dir("formal-lib", "Yiannis Charalambous"))
        cache.mkdir(parents=True, exist_ok=True)
        with open(cache / file_id, "wb") as file:
            pickle.dump(obj=result, file=file, protocol=-1)

    def _load_cached(self, properties: Any) -> Any:
        """Loads the verification results from a cached directory."""
        file_id: str = self._compute_cache_id(properties)
        logger.info(f"Searching cache ID: {file_id}")

        cache: Path = Path(user_cache_dir("formal-lib", "Yiannis Charalambous"))
        filename: Path = cache / file_id
        if cache.exists() and filename.exists() and filename.is_file():
            with open(filename, "rb") as file:
                data: bytes = pickle.load(file=file)
                logger.info("Using cached result")
                return data

        logger.info("Cache not found...")
        return None

    def verify_source(
        self,
        *source_paths: FilePath | DirectoryPath,
        file_paths: list[FilePath] | None = None,
        include_paths: list[DirectoryPath] | None = None,
        timeout: int | None = None,
        cwd: Path | None = None,
    ) -> VerifierOutput:
        """Verifies source_file."""

        timeout = timeout or self.default_timeout

        # Resolve appropriate paths
        assert len(source_paths) ^ (
            len(file_paths)
            if file_paths
            else False or len(include_paths) if include_paths else False
        )
        sources: list[FilePath | DirectoryPath] = list(source_paths)
        if not source_paths:
            assert file_paths and include_paths
            sources = cast(list[FilePath | DirectoryPath], file_paths + include_paths)

        resolved_cwd = cwd or Path(os.getcwd())

        if self.regex_spec.cache_properties:
            cache_props = self.regex_spec.cache_properties(
                self.base_cmd, sources, timeout, resolved_cwd
            )
        else:
            cache_props = [str(self.base_cmd), timeout, [str(s) for s in sources]]

        if self.enable_cache:
            cached = self._load_cached(cache_props)
            if cached is not None:
                return cached

        result: CompletedProcess
        duration: float
        result, duration = self.run_command(
            cmd=str(self.base_cmd).split(" ") + [str(s) for s in sources],
            cwd=resolved_cwd,
            process_timeout=timeout,
        )

        output = IssueSpecOutputParser(self.regex_spec).parse_output(
            exit_success=self.exit_success,
            return_code=result.returncode,
            output=result.stdout.decode("utf-8"),
            duration=duration,
        )

        if self.enable_cache:
            self._save_cached(cache_props, output)

        return output

    def run_command(
        self,
        cmd: list[str],
        cwd: Path,
        process_timeout: float | None,
    ) -> tuple[CompletedProcess, float]:
        """Runs the verifier."""

        # Add slack time to process to allow verifier to timeout and end gracefully.
        process_timeout = (
            process_timeout + _PROCESS_TIMEOUT_SLACK_SECONDS
            if process_timeout
            else None
        )
        # Measure execution time
        start_time = perf_counter()

        # Run verifier from solution working_dir and get output
        process: CompletedProcess = run(
            cmd,
            cwd=cwd,
            timeout=process_timeout,
            stdout=PIPE,
            stderr=STDOUT,
            check=False,
        )
        duration: float = perf_counter() - start_time

        return process, duration
