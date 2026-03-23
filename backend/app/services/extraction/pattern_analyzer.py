import re
import os
import json
import logging
from typing import Dict, Any, List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

class PatternAnalyzer:
    """
    Generalized Pattern Engine for Data Extraction values.
    Replaces hardcoded regexes with a centralized registry (heuristics.json),
    allowing updates without core parser modifications.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PatternAnalyzer, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
        
    def _initialize(self):
        self.rules = {}
        self.compiled_regexes = {}
        self.compiled_guards = {}
        self._load_heuristics()
        
    def _load_heuristics(self):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            heuristics_path = os.path.join(current_dir, "heuristics.json")
            
            with open(heuristics_path, "r", encoding="utf-8") as f:
                self.rules = json.load(f)
                
            # Precompile main patterns
            for key, val in self.rules.get("patterns", {}).items():
                if isinstance(val, dict) and "regex" in val:
                    # Default: ignore case for robust matching unless specified
                    self.compiled_regexes[key] = re.compile(val["regex"], re.IGNORECASE)
                if isinstance(val, dict) and "multi_regex" in val:
                    self.compiled_regexes[f"{key}_multi"] = re.compile(val["multi_regex"], re.IGNORECASE)
                    
            # Precompile guards
            guards = self.rules.get("guards", {}).get("protected_values", {})
            for key, regex_str in guards.items():
                # port needs strict case originally, but we'll use regex as written
                if key == "port":
                    self.compiled_guards[key] = re.compile(regex_str)
                else:
                    self.compiled_guards[key] = re.compile(regex_str, re.IGNORECASE)
                    
            logger.info(f"[PatternAnalyzer] Initialized with {len(self.compiled_regexes)} patterns and {len(self.compiled_guards)} guards.")
        except Exception as e:
            logger.error(f"[PatternAnalyzer] Failed to load heuristics.json: {e}")
            self.rules = {"patterns": {}, "keywords": {}, "guards": {}}

    def get_keywords(self, category: str) -> frozenset:
        """Get pre-defined frozen sets of keywords."""
        if category in self.rules.get("keywords", {}):
            return frozenset(self.rules["keywords"][category])
        if "labels" in self.rules.get("keywords", {}) and category in self.rules["keywords"]["labels"]:
            return frozenset(self.rules["keywords"]["labels"][category])
        return frozenset()

    def is_header_label(self, val: str) -> bool:
        """Check if the value is an exact match for a known structural header label (e.g. '도착항', 'POL')."""
        v = str(val).strip().lower()
        if not v:
            return False
        labels_dict = self.rules.get("keywords", {}).get("labels", {})
        for label_list in labels_dict.values():
            if v in [str(lbl).lower() for lbl in label_list]:
                return True
        return False

    def is_port_like(self, val: str) -> bool:
        val = str(val).strip()
        # Uses strict case (no IGNORECASE) for port codes so "Busan" vs "KRPUS" correctly differ
        # Re-compiling specifically without IGNORECASE since global might use IGNORECASE
        port_pattern = self.rules.get("patterns", {}).get("port_code", {}).get("regex", r'^[A-Z]{2,5}$')
        multi_port = self.rules.get("patterns", {}).get("port_code", {}).get("multi_regex", r'^[A-Z]{2,5}[/,]\s*[A-Z]{2,5}')
        
        if re.match(port_pattern, val): return True
        if re.match(multi_port, val): return True
        return False

    def is_date_like(self, val: str) -> bool:
        val = str(val).strip()
        if "date" in self.compiled_regexes and self.compiled_regexes["date"].match(val):
            return True
            
        serial_rules = self.rules.get("patterns", {}).get("serial_date", {})
        if "serial_date" in self.compiled_regexes and self.compiled_regexes["serial_date"].match(val):
            try:
                n = int(val)
                return serial_rules.get("min", 30000) < n < serial_rules.get("max", 60000)
            except ValueError:
                pass
        return False

    def normalize_date(self, val: str) -> str:
        """Normalize date value, including Excel serial dates."""
        val = str(val).strip()
        serial_rules = self.rules.get("patterns", {}).get("serial_date", {})
        if "serial_date" in self.compiled_regexes and self.compiled_regexes["serial_date"].match(val):
            try:
                from datetime import datetime, timedelta
                n = int(val)
                if serial_rules.get("min", 30000) < n < serial_rules.get("max", 60000):
                    dt = datetime(1899, 12, 30) + timedelta(days=n)
                    return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        return val

    def is_money_like(self, val: str) -> bool:
        val = str(val).strip()
        if not val:
            return False
        if "money" in self.compiled_regexes and self.compiled_regexes["money"].match(val):
            if re.search(r'\d', val):
                return True
        return False

    def is_currency_code(self, val: str) -> bool:
        if "currency_code" in self.compiled_regexes:
            return bool(self.compiled_regexes["currency_code"].match(str(val).strip()))
        return False

    def is_service_mode(self, val: str) -> bool:
        if "service_mode" in self.compiled_regexes:
            return bool(self.compiled_regexes["service_mode"].match(str(val).strip()))
        return False

    def get_validity_range(self, val: str):
        if "validity_range" in self.compiled_regexes:
            return self.compiled_regexes["validity_range"].search(str(val).strip())
        return None

    def get_route_phrase(self, val: str):
        if "route_phrase" in self.compiled_regexes:
            return self.compiled_regexes["route_phrase"].search(str(val).strip())
        return None

    def get_via_phrase(self, val: str):
        if "via_phrase" in self.compiled_regexes:
            return self.compiled_regexes["via_phrase"].search(str(val).strip())
        return None
        
    def is_protected_value(self, val: str) -> bool:
        """Check against destructible data guards (e.g. before extract_digits runs)."""
        v = str(val).strip()
        if "date" in self.compiled_guards and self.compiled_guards["date"].search(v): return True
        if "equipment" in self.compiled_guards and self.compiled_guards["equipment"].match(v): return True
        if "port" in self.compiled_guards and self.compiled_guards["port"].match(v): return True
        if "service_mode" in self.compiled_guards and self.compiled_guards["service_mode"].match(v): return True
        return False
        
    def is_safeguarded_geodata(self, val: str) -> bool:
        """Check if string is a known geographic coordinate format that shouldn't be split."""
        v = str(val).strip()
        guards = self.rules.get("guards", {}).get("split_delimiter_geo_safe", [])
        for pattern_str in guards:
            if re.match(pattern_str, v):
                return True
                
        # Guard "City, Country" like "BANGKOK, THAILAND"
        parts = [p.strip() for p in v.split(',')]
        if len(parts) == 2:
            country_candidate = parts[1].upper()
            known_countries = self.rules.get("keywords", {}).get("countries", [])
            if country_candidate in (c.upper() for c in known_countries):
                return True
                
        return False

# Global Singleton
analyzer = PatternAnalyzer()
