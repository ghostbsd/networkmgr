"""Logging infrastructure for NetworkMgr.

Provides centralized, formatted logging to stdout/stderr when verbose mode
is enabled via the `--verbose` / `-v` command-line argument.
"""

import logging
import sys

_VERBOSE = False
logger = logging.getLogger('networkmgr')


def set_verbose(enabled=True):
    """Enable or disable verbose debug output to stdout."""
    global _VERBOSE
    _VERBOSE = bool(enabled)
    level = logging.DEBUG if _VERBOSE else logging.INFO
    logger.setLevel(level)

    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def is_verbose():
    """Return True if verbose logging is currently enabled."""
    return _VERBOSE


def log_debug(msg, *args):
    """Emit a debug-level log message if verbose mode is active."""
    if _VERBOSE:
        logger.debug(msg, *args)


def log_info(msg, *args):
    """Emit an info-level log message if verbose mode is active."""
    if _VERBOSE:
        logger.info(msg, *args)


def log_warning(msg, *args):
    """Emit a warning-level log message if verbose mode is active."""
    if _VERBOSE:
        logger.warning(msg, *args)


def log_error(msg, *args):
    """Emit an error-level log message if verbose mode is active."""
    if _VERBOSE:
        logger.error(msg, *args)
