"""Hardcade Table-Tennis Rules Engine & Fleet Squad Elevation System.

Grounds fleet autonomous pongs in official table-tennis match rules:
1. Game is first to 11 points, must win by 2.
2. At 10-10, enter deuce. Continue until one side leads by 2.
3. Serve alternates every 2 points before deuce.
4. At deuce, serve alternates every 1 point.
5. Configurable best-of-3, best-of-5 (default), best-of-7 match formats.
6. Eliminates fake single-game scores like 51-0.
7. Anti-cheat invariants: no impossible score transitions, no double-awarded
   rally, no match continuing after clinch, server rotation integrity.
8. Squad progression & fighter elevation layer.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Set


class HardcadePongError(Exception):
    """Base exception for Hardcade Pong rules violations."""
    pass


class MatchAlreadyClinchedError(HardcadePongError):
    """Raised when an event is recorded on an already clinched match."""
    pass


class InvalidScorerError(HardcadePongError):
    """Raised when scorer is not recognized as player_a or player_b."""
    pass


class ImpossibleScoreError(HardcadePongError):
    """Raised when an impossible score transition or single-game score is asserted."""
    pass


@dataclass
class PointEvent:
    match_id: str
    game_index: int
    event_id: str
    player_a: str
    player_b: str
    scorer: str
    score_a: int
    score_b: int
    games_a: int
    games_b: int
    server: str
    deuce: bool
    rally_index: int
    verified_by: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "game_index": self.game_index,
            "event_id": self.event_id,
            "player_a": self.player_a,
            "player_b": self.player_b,
            "scorer": self.scorer,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "games_a": self.games_a,
            "games_b": self.games_b,
            "server": self.server,
            "deuce": self.deuce,
            "rally_index": self.rally_index,
            "verified_by": self.verified_by,
            "timestamp": self.timestamp,
        }


@dataclass
class CompletedGame:
    game_index: int
    score_a: int
    score_b: int
    winner: str
    is_shutout: bool      # 11-0 perfect game
    is_deuce_win: bool    # won after 10-10 deuce
    total_rallies: int


@dataclass
class FighterStats:
    name: str
    matches_played: int = 0
    matches_won: int = 0
    matches_lost: int = 0
    games_won: int = 0
    games_lost: int = 0
    points_scored: int = 0
    points_conceded: int = 0
    current_streak: int = 0
    best_streak: int = 0
    deuce_wins: int = 0
    comeback_wins: int = 0
    clean_sweeps: int = 0
    shutouts: int = 0
    touchdowns_verified: int = 0
    elevation_priority: int = 0

    @property
    def game_differential(self) -> int:
        return self.games_won - self.games_lost

    @property
    def point_differential(self) -> int:
        return self.points_scored - self.points_conceded

    def record_match_result(self, won: bool, games_for: int, games_against: int,
                            points_for: int, points_against: int, deuce_wins: int,
                            is_shutout: bool, was_comeback: bool, is_sweep: bool):
        self.matches_played += 1
        self.games_won += games_for
        self.games_lost += games_against
        self.points_scored += points_for
        self.points_conceded += points_against
        self.deuce_wins += deuce_wins
        if is_shutout:
            self.shutouts += 1

        if won:
            self.matches_won += 1
            self.current_streak += 1
            if self.current_streak > self.best_streak:
                self.best_streak = self.current_streak
            if was_comeback:
                self.comeback_wins += 1
            if is_sweep:
                self.clean_sweeps += 1
            self.elevation_priority += 10
        else:
            self.matches_lost += 1
            self.current_streak = 0
            self.elevation_priority = max(0, self.elevation_priority - 3)


class HardcadePongMatch:
    """Manages an official table-tennis match between two nodes/fighters."""

    def __init__(
        self,
        player_a: str,
        player_b: str,
        best_of: int = 5,
        match_id: Optional[str] = None,
        initial_server: Optional[str] = None
    ):
        if best_of not in (1, 3, 5, 7):
            raise ValueError(f"best_of must be 1, 3, 5, or 7; got {best_of}")

        self.match_id = match_id or f"match_{uuid.uuid4().hex[:12]}"
        self.player_a = player_a
        self.player_b = player_b
        self.best_of = best_of
        self.games_needed = (best_of // 2) + 1

        self.game_index = 1
        self.score_a = 0
        self.score_b = 0
        self.games_a = 0
        self.games_b = 0

        self.game_initial_server = initial_server or player_a
        self.current_server = self.game_initial_server
        self.rally_index = 0
        self.game_rally_count = 0

        self.match_winner: Optional[str] = None
        self.is_sweep: bool = False
        self.completed_games: List[CompletedGame] = []
        self.event_history: List[PointEvent] = []
        self._seen_event_ids: Set[str] = set()

    @property
    def is_deuce(self) -> bool:
        return self.score_a >= 10 and self.score_b >= 10 and abs(self.score_a - self.score_b) < 2

    def _determine_server(self, score_a: int, score_b: int) -> str:
        """Calculate server based on table-tennis rules."""
        total_points = score_a + score_b
        other_player = self.player_b if self.game_initial_server == self.player_a else self.player_a

        if score_a >= 10 and score_b >= 10:
            # Deuce: server alternates on every single point
            points_since_deuce = total_points - 20
            if points_since_deuce % 2 == 0:
                return self.game_initial_server
            else:
                return other_player
        else:
            # Normal: server alternates every 2 points
            service_rotation = (total_points // 2) % 2
            return self.game_initial_server if service_rotation == 0 else other_player

    def record_point(
        self,
        scorer: str,
        event_id: Optional[str] = None,
        verified_by: str = "hardcade_referee",
        timestamp: Optional[str] = None
    ) -> PointEvent:
        """Award a point to scorer with strict invariant enforcement."""
        if self.match_winner is not None:
            raise MatchAlreadyClinchedError(
                f"Match {self.match_id} already won by {self.match_winner} ({self.games_a}-{self.games_b})."
            )

        if scorer not in (self.player_a, self.player_b):
            raise InvalidScorerError(f"Scorer '{scorer}' is not '{self.player_a}' or '{self.player_b}'")

        evt_id = event_id or f"evt_{self.match_id}_{self.rally_index + 1}"
        if evt_id in self._seen_event_ids:
            # Idempotent deduplication: return existing event
            for ev in self.event_history:
                if ev.event_id == evt_id:
                    return ev

        ts = timestamp or datetime.now(timezone.utc).isoformat()

        # Award point
        if scorer == self.player_a:
            self.score_a += 1
        else:
            self.score_b += 1

        self.rally_index += 1
        self.game_rally_count += 1
        self._seen_event_ids.add(evt_id)

        # Update server
        self.current_server = self._determine_server(self.score_a, self.score_b)

        point_event = PointEvent(
            match_id=self.match_id,
            game_index=self.game_index,
            event_id=evt_id,
            player_a=self.player_a,
            player_b=self.player_b,
            scorer=scorer,
            score_a=self.score_a,
            score_b=self.score_b,
            games_a=self.games_a,
            games_b=self.games_b,
            server=self.current_server,
            deuce=self.is_deuce,
            rally_index=self.rally_index,
            verified_by=verified_by,
            timestamp=ts
        )
        self.event_history.append(point_event)

        # Check if game won (first to 11, must win by 2)
        if (self.score_a >= 11 or self.score_b >= 11) and abs(self.score_a - self.score_b) >= 2:
            self._finalize_game()

        return point_event

    def _finalize_game(self):
        game_winner = self.player_a if self.score_a > self.score_b else self.player_b
        is_shutout = (self.score_a == 11 and self.score_b == 0) or (self.score_b == 11 and self.score_a == 0)
        is_deuce_win = (self.score_a > 11 or self.score_b > 11)

        completed = CompletedGame(
            game_index=self.game_index,
            score_a=self.score_a,
            score_b=self.score_b,
            winner=game_winner,
            is_shutout=is_shutout,
            is_deuce_win=is_deuce_win,
            total_rallies=self.game_rally_count
        )
        self.completed_games.append(completed)

        if game_winner == self.player_a:
            self.games_a += 1
        else:
            self.games_b += 1

        # Check match clinch
        if self.games_a >= self.games_needed:
            self.match_winner = self.player_a
            self.is_sweep = (self.games_b == 0)
        elif self.games_b >= self.games_needed:
            self.match_winner = self.player_b
            self.is_sweep = (self.games_a == 0)
        else:
            # Advance to next game
            self.game_index += 1
            self.score_a = 0
            self.score_b = 0
            self.game_rally_count = 0
            # Next game server alternates initial server
            self.game_initial_server = (
                self.player_b if self.game_initial_server == self.player_a else self.player_a
            )
            self.current_server = self.game_initial_server

    def get_scoreboard(self) -> Dict[str, Any]:
        """Return the complete Hardcade scoreboard."""
        return {
            "match_id": self.match_id,
            "format": f"Best of {self.best_of}",
            "status": "CLINCHED" if self.match_winner else "IN_PROGRESS",
            "winner": self.match_winner,
            "games_a": self.games_a,
            "games_b": self.games_b,
            "current_game": {
                "game_index": self.game_index,
                "score_a": self.score_a,
                "score_b": self.score_b,
                "server": self.current_server,
                "is_deuce": self.is_deuce,
            },
            "completed_games": [
                {
                    "game": g.game_index,
                    "score": f"{g.score_a}-{g.score_b}",
                    "winner": g.winner,
                    "shutout": g.is_shutout,
                    "deuce_win": g.is_deuce_win
                }
                for g in self.completed_games
            ],
            "total_rallies": self.rally_index,
            "is_sweep": self.is_sweep
        }


class HardcadeSquadProgression:
    """Manages squad ladder, fighter stats, and elevation priority."""

    def __init__(self):
        self.fighters: Dict[str, FighterStats] = {}

    def get_fighter(self, name: str) -> FighterStats:
        if name not in self.fighters:
            self.fighters[name] = FighterStats(name=name)
        return self.fighters[name]

    def record_match(self, match: HardcadePongMatch):
        if not match.match_winner:
            return

        f_a = self.get_fighter(match.player_a)
        f_b = self.get_fighter(match.player_b)

        total_pts_a = sum(g.score_a for g in match.completed_games)
        total_pts_b = sum(g.score_b for g in match.completed_games)

        deuces_a = sum(1 for g in match.completed_games if g.winner == match.player_a and g.is_deuce_win)
        deuces_b = sum(1 for g in match.completed_games if g.winner == match.player_b and g.is_deuce_win)

        shutouts_a = any(g.winner == match.player_a and g.is_shutout for g in match.completed_games)
        shutouts_b = any(g.winner == match.player_b and g.is_shutout for g in match.completed_games)

        # Check comeback: e.g. down 0-2 and won 3-2 in best-of-5
        comeback_a = False
        comeback_b = False
        if len(match.completed_games) >= 3:
            first_two = [g.winner for g in match.completed_games[:2]]
            if match.match_winner == match.player_a and all(w == match.player_b for w in first_two):
                comeback_a = True
            elif match.match_winner == match.player_b and all(w == match.player_a for w in first_two):
                comeback_b = True

        f_a.record_match_result(
            won=(match.match_winner == match.player_a),
            games_for=match.games_a,
            games_against=match.games_b,
            points_for=total_pts_a,
            points_against=total_pts_b,
            deuce_wins=deuces_a,
            is_shutout=shutouts_a,
            was_comeback=comeback_a,
            is_sweep=(match.match_winner == match.player_a and match.is_sweep)
        )

        f_b.record_match_result(
            won=(match.match_winner == match.player_b),
            games_for=match.games_b,
            games_against=match.games_a,
            points_for=total_pts_b,
            points_against=total_pts_a,
            deuce_wins=deuces_b,
            is_shutout=shutouts_b,
            was_comeback=comeback_b,
            is_sweep=(match.match_winner == match.player_b and match.is_sweep)
        )

    def get_ladder(self) -> List[Dict[str, Any]]:
        """Return leaderboard ranked by elevation priority and match record."""
        sorted_fighters = sorted(
            self.fighters.values(),
            key=lambda f: (f.elevation_priority, f.matches_won, f.game_differential, f.point_differential),
            reverse=True
        )
        ladder = []
        for rank, f in enumerate(sorted_fighters, start=1):
            ladder.append({
                "rank": rank,
                "name": f.name,
                "elevation_priority": f.elevation_priority,
                "record": f"{f.matches_won}-{f.matches_lost}",
                "game_diff": f.game_differential,
                "point_diff": f.point_differential,
                "streak": f.current_streak,
                "sweeps": f.clean_sweeps,
                "shutouts": f.shutouts,
                "comebacks": f.comeback_wins,
                "deuce_wins": f.deuce_wins
            })
        return ladder
