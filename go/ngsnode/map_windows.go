//go:build windows

package main

import "os"

// mapFile reads the file into memory. A mapped file cannot be replaced on
// Windows, and the Python node replaces these files on every save, so the
// Windows build trades the page-cache saving for a plain copy.
func mapFile(path string) ([]byte, error) { return os.ReadFile(path) }

func unmapFile(b []byte) {}
