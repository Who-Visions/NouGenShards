"""Unit tests for NouGen Physical Peripheral Driver (HP ENVY Pro 6455)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from nougen_shards import physical_peripheral


def test_scan_document_success():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"status": "success", "file": "C:/temp/scan.png", "source": "flatbed"})
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = physical_peripheral.scan_document(output_path="C:/temp/scan.png", source="flatbed")

        assert result["status"] == "success"
        assert result["file"] == "C:/temp/scan.png"
        assert result["source"] == "flatbed"
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "--scan" in cmd
        assert "--source" in cmd
        assert "flatbed" in cmd
        assert "--out" in cmd
        assert "C:/temp/scan.png" in cmd
        assert kwargs.get("creationflags") == physical_peripheral._NO_WINDOW


def test_scan_document_error():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "WIA device not found"
        mock_run.return_value = mock_proc

        result = physical_peripheral.scan_document()

        assert result["status"] == "error"
        assert "WIA device not found" in result["error"]


def test_print_document_success():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"status": "success", "printer": "HP ENVY 6455 USB", "bytes_spooled": 1024})
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = physical_peripheral.print_document("C:/temp/doc.pdf", printer_name="HP ENVY 6455 USB", copies=2)

        assert result["status"] == "success"
        assert result["printer"] == "HP ENVY 6455 USB"
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "--print" in cmd
        assert "C:/temp/doc.pdf" in cmd
        assert "--printer" in cmd
        assert "HP ENVY 6455 USB" in cmd


def test_copy_document_success():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"status": "success", "copies": 3, "source": "feeder"})
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = physical_peripheral.copy_document(copies=3, source="feeder")

        assert result["status"] == "success"
        assert result["copies"] == 3
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "--copy" in cmd
        assert "3" in cmd
        assert "--source" in cmd
        assert "feeder" in cmd
