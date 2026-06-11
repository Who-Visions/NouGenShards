"""
Brain Scan Module: Discovers and normalizes local AI tool history.
"""
from .scanner import scan_environment
from .importer import run_import
from .reporters import print_scan_report, print_import_report
