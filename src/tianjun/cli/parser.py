from __future__ import annotations

from argparse import ArgumentParser

from . import build_parser


def create_parser() -> ArgumentParser:
    """Return the canonical Tianjun CLI parser.

    Command handlers still live in the package entry module during the first
    convergence step; this module gives future command extraction a stable
    import target without changing CLI behavior.
    """

    return build_parser()
