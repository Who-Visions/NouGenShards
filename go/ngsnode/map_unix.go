//go:build !windows

package main

import (
	"os"
	"syscall"
)

// mapFile maps the file read-only. The pages are file-backed, so they cost
// no heap and the OS can drop and re-read them under memory pressure.
func mapFile(path string) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	return syscall.Mmap(int(f.Fd()), 0, int(st.Size()), syscall.PROT_READ, syscall.MAP_SHARED)
}

func unmapFile(b []byte) { _ = syscall.Munmap(b) }
