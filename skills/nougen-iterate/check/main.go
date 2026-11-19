// iterate-check reads the round log in an ITERATE.md file and returns a
// verdict for the nougen-iterate contract.
//
// Exit codes: 0 = CONTINUE, 2 = STOP (plateau or round cap), 1 = VIOLATION
// (a kept round with red tests, or a malformed log).
//
// Usage: iterate-check [-plateau N] [-max-rounds N] ITERATE.md
package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
)

type Round struct {
	N            int
	Before       float64
	After        float64
	TestsGreen   bool
	LinesDelta   int
	Kept         bool
	HasReference bool
}

type Verdict struct {
	Code     int
	Status   string
	Reasons  []string
	Warnings []string
	Best     *Round
}

// ParseLog pulls rounds from the "## Round log" markdown table.
func ParseLog(r io.Reader) ([]Round, error) {
	var rounds []Round
	inLog := false
	sc := bufio.NewScanner(r)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "## ") {
			inLog = strings.EqualFold(strings.TrimPrefix(line, "## "), "Round log")
			continue
		}
		if !inLog || !strings.HasPrefix(line, "|") {
			continue
		}
		cells := strings.Split(strings.Trim(line, "|"), "|")
		for i := range cells {
			cells[i] = strings.TrimSpace(cells[i])
		}
		if len(cells) < 7 {
			continue
		}
		n, err := strconv.Atoi(cells[0])
		if err != nil {
			continue // header or separator row
		}
		before, after, err := parseScore(cells[3])
		if err != nil {
			return nil, fmt.Errorf("round %d: %w", n, err)
		}
		delta, _ := strconv.Atoi(strings.ReplaceAll(cells[5], "+", ""))
		tests := strings.ToLower(cells[4])
		rounds = append(rounds, Round{
			N: n, Before: before, After: after, LinesDelta: delta,
			TestsGreen:   tests == "pass" || tests == "green" || tests == "ok",
			Kept:         strings.HasPrefix(strings.ToLower(cells[6]), "kept"),
			HasReference: cells[2] != "" && cells[2] != "-",
		})
	}
	return rounds, sc.Err()
}

func parseScore(s string) (float64, float64, error) {
	parts := strings.Split(s, "->")
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("score %q is not 'before -> after'", s)
	}
	b, err1 := strconv.ParseFloat(strings.TrimSpace(parts[0]), 64)
	a, err2 := strconv.ParseFloat(strings.TrimSpace(parts[1]), 64)
	if err1 != nil || err2 != nil {
		return 0, 0, fmt.Errorf("score %q is not numeric", s)
	}
	return b, a, nil
}

// Evaluate applies the contract: the regression gate, the plateau stop, the
// round cap, and flags for code growth with no gain and missing references.
func Evaluate(rounds []Round, plateau, maxRounds int) Verdict {
	v := Verdict{Code: 0, Status: "CONTINUE"}
	stall := 0
	for i := range rounds {
		r := &rounds[i]
		if r.Kept && !r.TestsGreen {
			v.Reasons = append(v.Reasons, fmt.Sprintf("round %d kept with red tests (must revert)", r.N))
		}
		if !r.HasReference {
			v.Warnings = append(v.Warnings, fmt.Sprintf("round %d has no reference source", r.N))
		}
		gain := r.Kept && r.After > r.Before
		if r.Kept && r.LinesDelta > 0 && r.After <= r.Before {
			v.Warnings = append(v.Warnings, fmt.Sprintf("round %d added %d lines with no score gain", r.N, r.LinesDelta))
		}
		if gain {
			stall = 0
		} else {
			stall++
		}
		if r.Kept && r.TestsGreen && (v.Best == nil || r.After > v.Best.After) {
			v.Best = r
		}
	}
	switch {
	case len(v.Reasons) > 0:
		v.Code, v.Status = 1, "VIOLATION"
	case plateau > 0 && stall >= plateau:
		v.Code, v.Status = 2, "STOP"
		v.Reasons = append(v.Reasons, fmt.Sprintf("plateau: %d rounds with no rubric gain", stall))
	case maxRounds > 0 && len(rounds) >= maxRounds:
		v.Code, v.Status = 2, "STOP"
		v.Reasons = append(v.Reasons, fmt.Sprintf("round cap %d reached", maxRounds))
	}
	return v
}

func main() {
	plateau := flag.Int("plateau", 3, "consecutive no-gain rounds that trigger STOP")
	maxRounds := flag.Int("max-rounds", 0, "round cap (0 = none)")
	flag.Parse()
	if flag.NArg() != 1 {
		fmt.Fprintln(os.Stderr, "usage: iterate-check [-plateau N] [-max-rounds N] ITERATE.md")
		os.Exit(1)
	}
	f, err := os.Open(flag.Arg(0))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer f.Close()
	rounds, err := ParseLog(f)
	if err != nil {
		fmt.Println("VIOLATION:", err)
		os.Exit(1)
	}
	v := Evaluate(rounds, *plateau, *maxRounds)
	fmt.Printf("%s rounds=%d\n", v.Status, len(rounds))
	if v.Best != nil {
		fmt.Printf("best: round %d score %.1f\n", v.Best.N, v.Best.After)
	}
	for _, s := range v.Reasons {
		fmt.Println("reason:", s)
	}
	for _, s := range v.Warnings {
		fmt.Println("warn:", s)
	}
	os.Exit(v.Code)
}
