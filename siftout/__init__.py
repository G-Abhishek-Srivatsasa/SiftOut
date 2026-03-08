"""
Siftout
~~~~~~~

Smart, automated workspace cleaner and security hardener for Python projects.

    >>> from siftout import Janitor
    >>> j = Janitor(extra_patterns=["*.bak"], dry_run=True)
    >>> report = j.self_destruct()
    >>> print(report)

:copyright: 2025 Abhishek Srivatsasa Guntur & Devansh Singh
:license: MIT
"""

from .hardware import CleanReport, Janitor, SecureReport

__all__ = ["Janitor", "CleanReport", "SecureReport"]
__version__ = "1.0.0"
__author__ = "Abhishek Srivatsasa Guntur, Devansh Singh"