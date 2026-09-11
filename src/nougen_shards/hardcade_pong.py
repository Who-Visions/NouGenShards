"""
Hardcade Table-Tennis Rules Engine (Leg 20260908T230836Z).
Enforces authentic table-tennis scoring, deuce transitions, serve rotations,
best-of-N match clinches, and anti-cheat idempotency.
"""
import uuid
import time
from typing import Optional, Dict, Any, List

class HardcadePongMatch:
    def __init__(
        self,
        player_a: str = "blade",
        player_b: str = "whoart",
        best_of: int = 5,
        match_id: Optional[str] = None,
        initial_server: Optional[str] = None
    ):
        if best_of % 2 == 0 or best_of < 1:
            raise ValueError("best_of must be an odd positive integer (e.g. 1, 3, 5, 7)")
        
        self.match_id = match_id or f"match_{uuid.uuid4().hex[:8]}"
        self.player_a = player_a
        self.player_b = player_b
        self.best_of = best_of
        self.games_to_win = (best_of // 2) + 1
        
        self.games_a = 0
        self.games_b = 0
        self.current_game = 1
        
        self.score_a = 0
        self.score_b = 0
        
        self.initial_server = initial_server or player_a
        self.game_initial_server = self.initial_server
        self.current_server = self.game_initial_server
        
        self.rally_index = 0
        self.events: List[Dict[str, Any]] = []
        self.seen_events = set()
        self.match_winner: Optional[str] = None

    @property
    def is_deuce(self) -> bool:
        return self.score_a >= 10 and self.score_b >= 10 and self.score_a == self.score_b

    @property
    def in_overtime(self) -> bool:
        return self.score_a >= 10 and self.score_b >= 10

    def _determine_server(self) -> str:
        total_pts = self.score_a + self.score_b
        other_player = self.player_b if self.game_initial_server == self.player_a else self.player_a
        
        if total_pts < 20:
            serves_done = total_pts // 2
            return self.game_initial_server if (serves_done % 2 == 0) else other_player
        else:
            # Overtime / deuce: rotates every 1 serve
            overtime_pts = total_pts - 20
            server_at_20 = self.game_initial_server if ((20 // 2) % 2 == 0) else other_player
            return other_player if (overtime_pts % 2 == 1) else server_at_20

    def record_point(
        self,
        scorer: str,
        event_id: Optional[str] = None,
        verified_by: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.match_winner:
            raise ValueError(f"Match already concluded: {self.match_winner} clinched {self.games_a}-{self.games_b}")
            
        if scorer not in (self.player_a, self.player_b):
            raise ValueError(f"Invalid scorer {scorer}; must be {self.player_a} or {self.player_b}")

        if event_id:
            if event_id in self.seen_events:
                return {"status": "ignored_duplicate", "event_id": event_id}
            self.seen_events.add(event_id)
        else:
            event_id = f"ev_{uuid.uuid4().hex[:8]}"

        self.rally_index += 1
        if scorer == self.player_a:
            self.score_a += 1
        else:
            self.score_b += 1

        game_winner = None
        if self.score_a >= 11 and (self.score_a - self.score_b) >= 2:
            game_winner = self.player_a
        elif self.score_b >= 11 and (self.score_b - self.score_a) >= 2:
            game_winner = self.player_b

        is_shutout = (self.score_a == 11 and self.score_b == 0) or (self.score_b == 11 and self.score_a == 0)
        
        event = {
            "event_id": event_id,
            "match_id": self.match_id,
            "game_index": self.current_game,
            "player_a": self.player_a,
            "player_b": self.player_b,
            "scorer": scorer,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "games_a": self.games_a,
            "games_b": self.games_b,
            "server": self._determine_server(),
            "deuce": self.is_deuce,
            "overtime": self.in_overtime,
            "rally_index": self.rally_index,
            "game_winner": game_winner,
            "is_shutout": is_shutout,
            "verified_by": verified_by or "referee",
            "timestamp": time.time()
        }

        if game_winner:
            if game_winner == self.player_a:
                self.games_a += 1
            else:
                self.games_b += 1
            event["games_a"] = self.games_a
            event["games_b"] = self.games_b

            if self.games_a == self.games_to_win:
                self.match_winner = self.player_a
            elif self.games_b == self.games_to_win:
                self.match_winner = self.player_b
            
            event["match_winner"] = self.match_winner
            
            if not self.match_winner:
                self.current_game += 1
                self.score_a = 0
                self.score_b = 0
                other_player = self.player_b if self.game_initial_server == self.player_a else self.player_a
                self.game_initial_server = other_player
                self.current_server = self.game_initial_server
        else:
            self.current_server = self._determine_server()
            event["server"] = self.current_server

        self.events.append(event)
        return event

    def snapshot(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "player_a": self.player_a,
            "player_b": self.player_b,
            "best_of": self.best_of,
            "current_game": self.current_game,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "games_a": self.games_a,
            "games_b": self.games_b,
            "server": self.current_server,
            "deuce": self.is_deuce,
            "match_winner": self.match_winner,
            "rally_index": self.rally_index
        }
