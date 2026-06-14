import os
import re
import math
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

class TemporalNexusShard:
    def __init__(self, file_path: str, base_utility: float = 1.0):
        self.file_path = file_path
        self.base_utility = base_utility
        self.system_ingestion_time = time.time()
        
        # Core Dimension Storage
        self.physical_dimensions: Dict[str, float] = {}
        self.semantic_dimensions: Dict[str, Any] = {}
        self.bitemporal_dimensions: Dict[str, float] = {}
        self.logical_clock: int = 0
        self.access_history: List[float] = []

        self._extract_physical_substrate()

    def _extract_physical_substrate(self) -> None:
        """Layer 1: Extract MACB physical system timestamps."""
        logically_valid = os.path.exists(self.file_path)
        if not logically_valid:
            raise FileNotFoundError(f"Target substrate file not found: {self.file_path}")
             
        stat = os.stat(self.file_path)
        self.physical_dimensions['btime'] = getattr(stat, 'st_birthtime', stat.st_ctime)
        self.physical_dimensions['mtime'] = stat.st_mtime
        self.physical_dimensions['ctime'] = stat.st_ctime
        self.physical_dimensions['atime'] = stat.st_atime
        
        # Initialize default Bi-Temporal tracking parameters
        self.bitemporal_dimensions['transaction_time'] = self.system_ingestion_time
        self.bitemporal_dimensions['valid_time_start'] = self.physical_dimensions['mtime']

    def parse_payload_anchors(self, raw_text: str) -> None:
        """Layer 2 & 3: Extract semantic temporal expressions inside document text."""
        # Look for typical arXiv date formats or standard ISO dates within text
        arxiv_patterns = [
            r"arXiv:\d{4}\.\d{4,5}",
            r"v\d+\s+\[([0-9a-zA-Z\s,]+)\]",
            r"(19|20)\d{2}[-\/.](0[1-9]|1[012])[-\/.](0[1-9]|[12][0-9]|3[01])"
        ]
        
        found_anchors = []
        for pattern in arxiv_patterns:
            matches = re.findall(pattern, raw_text)
            if matches:
                found_anchors.extend(matches)
                
        self.semantic_dimensions['extracted_anchors'] = found_anchors
        
        # Try to guess real valid_time from text (fallback to modification epoch if none found)
        year_match = re.search(r"\b(19|20)\d{2}\b", raw_text)
        if year_match:
            # Anchor to January 1st of the discovered publication year
            dt = datetime(year=int(year_match.group(0)), month=1, day=1)
            self.bitemporal_dimensions['valid_time_start'] = dt.timestamp()

    def register_access_event(self) -> None:
        """Tracks access actions to continually calculate velocity and momentum."""
        self.access_history.append(time.time())
        self.logical_clock += 1


class KronosEngine:
    def __init__(self, half_life_days: float = 30.0, momentum_lambda: float = 0.0001):
        self.tau: float = half_life_days * 86400.0  # Convert days to seconds
        self.lambd: float = momentum_lambda       # Momentum decay coefficient

    def calculate_cognitive_utility(self, shard: TemporalNexusShard) -> float:
        """Computes current dynamic utility utilizing exponential half-life decay."""
        now = time.time()
        dt = now - shard.physical_dimensions.get('mtime', now)
        
        # U(t) = U0 * 2^(-dt / tau)
        exponent = -(dt / self.tau)
        current_utility = shard.base_utility * math.pow(2.0, exponent)
        return round(current_utility, 6)

    def calculate_temporal_momentum(self, shard: TemporalNexusShard) -> float:
        """Computes current access speed momentum based on linear/exponential history."""
        now = time.time()
        if not shard.access_history:
            return 0.0
            
        # M(t) = sum( e^(-lambda * (now - t_i)) )
        momentum = sum(math.exp(-self.lambd * (now - t_i)) for t_i in shard.access_history)
        return round(momentum, 6)

    def calculate_alignment_coefficient(self, shard: TemporalNexusShard) -> float:
        """Computes divergence ratio between System Ingestion Time and Semantic Valid Time."""
        t_sys = shard.bitemporal_dimensions['transaction_time']
        t_val = shard.bitemporal_dimensions['valid_time_start']
        
        delta = abs(t_sys - t_val)
        alignment = 1.0 / (1.0 + math.log(1.0 + delta))
        return round(alignment, 6)

    def synthesize_temporal_profile(self, shard: TemporalNexusShard) -> Dict[str, Any]:
        """Generates a comprehensive temporal digest for multi-agent retrieval sorting."""
        return {
            "file": os.path.basename(shard.file_path),
            "logical_sequence_id": shard.logical_clock,
            "metrics": {
                "cognitive_utility": self.calculate_cognitive_utility(shard),
                "temporal_momentum": self.calculate_temporal_momentum(shard),
                "bitemporal_alignment": self.calculate_alignment_coefficient(shard)
            }
        }
