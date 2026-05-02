"""GitHub Actions integration: PR comment bot, merge-blocking exit codes."""

from .github import (
    EXIT_CRITICAL,
    EXIT_OK,
    EXIT_WARNING,
    build_pr_comment,
    severity_to_exit_code,
)

__all__ = [
    "EXIT_CRITICAL",
    "EXIT_OK",
    "EXIT_WARNING",
    "build_pr_comment",
    "severity_to_exit_code",
]
