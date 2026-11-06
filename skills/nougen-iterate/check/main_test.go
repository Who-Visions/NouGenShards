package main

import (
	"strings"
	"testing"
)

const header = "# ITERATE\n\n## Round log\n| round | change | ref source | score before -> after | tests | lines +/- | kept/reverted |\n|---|---|---|---|---|---|---|\n"

func run(t *testing.T, rows string, plateau, maxRounds int) Verdict {
	t.Helper()
	rounds, err := ParseLog(strings.NewReader(header + rows))
	if err != nil {
		t.Fatal(err)
	}
	return Evaluate(rounds, plateau, maxRounds)
}

func TestContinueOnGain(t *testing.T) {
	v := run(t, "| 1 | hero | awwwards | 10 -> 12 | pass | +40 | kept |\n", 3, 0)
	if v.Code != 0 || v.Best == nil || v.Best.N != 1 {
		t.Fatalf("want CONTINUE with best=1, got %+v", v)
	}
}

func TestPlateauStops(t *testing.T) {
	rows := "| 1 | a | r | 10 -> 12 | pass | +5 | kept |\n" +
		"| 2 | b | r | 12 -> 12 | pass | +30 | kept |\n" +
		"| 3 | c | r | 12 -> 11 | fail | +9 | reverted |\n" +
		"| 4 | none | r | 12 -> 12 | pass | 0 | kept |\n"
	v := run(t, rows, 3, 0)
	if v.Code != 2 || v.Best.N != 1 {
		t.Fatalf("want STOP with best=1, got %+v", v)
	}
	if len(v.Warnings) != 1 || !strings.Contains(v.Warnings[0], "round 2 added 30") {
		t.Fatalf("want bloat warning on round 2, got %v", v.Warnings)
	}
}

func TestKeptRedTestsIsViolation(t *testing.T) {
	v := run(t, "| 1 | x | r | 10 -> 14 | fail | +100 | kept |\n", 3, 0)
	if v.Code != 1 {
		t.Fatalf("want VIOLATION, got %+v", v)
	}
}

func TestRoundCapAndMissingRef(t *testing.T) {
	rows := "| 1 | a | - | 1 -> 2 | pass | 0 | kept |\n| 2 | b | r | 2 -> 3 | pass | -10 | kept |\n"
	v := run(t, rows, 3, 2)
	if v.Code != 2 || len(v.Warnings) != 1 {
		t.Fatalf("want STOP via cap and one missing-ref warning, got %+v", v)
	}
}

func TestBadScoreRejected(t *testing.T) {
	if _, err := ParseLog(strings.NewReader(header + "| 1 | a | r | better | pass | 0 | kept |\n")); err == nil {
		t.Fatal("want error on non-numeric score")
	}
}
