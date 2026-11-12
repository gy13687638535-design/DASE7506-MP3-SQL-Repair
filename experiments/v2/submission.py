"""Feedback-driven, offline CPU SQL repair controller.

Only action dictionaries touch benchmark tools; no benchmark files are opened.
"""
import json
from pathlib import Path
from collections import Counter

import sqlglot
from sqlglot import exp


def canonical(sql):
    try:
        return sqlglot.parse_one(sql, read="sqlite").sql(dialect="sqlite", normalize=True)
    except Exception:
        return sql.strip()


def safe(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql.encode()) > 16000:
        return False
    try:
        trees = sqlglot.parse(sql, read="sqlite")
        return len(trees) == 1 and isinstance(trees[0], (exp.Select, exp.SetOperation)) and not any(
            isinstance(n, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
                           exp.Command, exp.Into)) for n in trees[0].walk())
    except Exception:
        return False


class RepairAgent:
    def __init__(self, config=None):
        self.config = {"hints": True, "repairs": True, "schema": True,
                       "early_stop": True, "verify_weak_matches": True, **(config or {})}

    def act(self, observation):
        history = observation["history"]
        original = observation["issue_sql"]
        if not history:
            return {"tool": "check", "sql": original}
        checked = [h for h in history if h["tool"] == "check"]
        matches = [h for h in checked if h["observation"].get("matches_example")]
        weak = not any(cell is not None for row in observation["example"]["rows"] for cell in row)
        hints = [h for h in history if h["tool"] == "repair_hint"]
        if matches and self.config["early_stop"] and not self.config.get("refine_matches") and not (
                (self.config.get("verify_all_matches") or (weak and self.config["verify_weak_matches"])) and self.config["hints"] and
                (not hints or len(checked) == 1)):
            return {"tool": "submit", "sql": self.choose(checked, original, observation)}
        if observation["remaining"] <= 0:
            return {"tool": "submit", "sql": self.choose(checked, original, observation)}
        if self.config["hints"] and not hints:
            return {"tool": "repair_hint"}
        seen = {canonical(h["sql"]) for h in checked}
        schema_events = [h for h in history if h["tool"] == "schema"]
        schema = schema_events[0]["observation"] if schema_events else None
        if (self.config["repairs"] and self.config["schema"] and schema is None
                and len(checked) >= 2 and not checked[-1]["observation"].get("ok")
                and observation["remaining"] >= 2):
            return {"tool": "schema"}
        pool = []
        if hints:
            suggestions = hints[0]["observation"]
            counts = Counter(canonical(s) for s in suggestions if isinstance(s, str))
            for i, sql in enumerate(suggestions):
                if isinstance(sql, str):
                    pool.append((sql, "hint", 100 + counts[canonical(sql)] - i / 100))
        if self.config["repairs"]:
            from repairs import candidates
            for h in checked:
                edits = candidates(h["sql"], observation["task"]["question"],
                                   h["observation"], observation["example"], schema)
                if self.config.get("semantic"):
                    from semantic_repairs import candidates as semantic_candidates
                    edits.extend(semantic_candidates(h["sql"], observation["task"]["question"],
                                                     h["observation"], observation["example"], schema))
                for s, why, rank in edits:
                    if self.config.get("projection_first") and why == "public_projection":
                        rank += 30
                    rank += self.config.get("recency_bonus", 0) * (checked.index(h) / max(1,len(checked)-1))
                    pool.append((s,why,rank))
        if self.config.get("compose_projection"):
            from repairs import _projection
            if self.config.get("safe_projection"):
                from semantic_repairs import _alias_expanded_projection as _projection
            composed = []
            for s, why, rank in pool:
                try:
                    tree = sqlglot.parse_one(s, read='sqlite')
                    fixed = _projection(tree, observation['example'], schema) if isinstance(tree, exp.Select) else None
                    if fixed is not None:
                        composed.append((fixed.sql(dialect='sqlite'), why + '/projection', rank + 20))
                except Exception:
                    pass
            pool.extend(composed)
        pool = [(s, why, rank) for s, why, rank in pool if safe(s) and canonical(s) not in seen]
        if matches and self.config.get("hint_only_pass"):
            pool = [(s, why, rank) for s, why, rank in pool if why.startswith('hint')]
        if self.config.get("quality_priority") or (matches and self.config.get("refine_matches")):
            from ranking import quality
            q = observation['task']['question']
            example = observation['example']
            if matches and self.config.get("refine_matches"):
                best_quality = max(quality(h['sql'], q, example, schema) for h in matches)
                pool = [(s, why, rank) for s, why, rank in pool
                        if quality(s, q, example, schema) > best_quality + self.config.get('refine_margin', 0.75)]
            pool = [(s, why, rank + self.config.get('quality_priority', 0) * quality(s,q,example,schema))
                    for s,why,rank in pool]
        if pool:
            sql, _, _ = max(pool, key=lambda item: item[2])
            return {"tool": "check", "sql": sql}
        if matches:
            return {"tool":"submit", "sql":self.choose(checked,original,observation)}
        if self.config["repairs"] and self.config["schema"] and schema is None and observation["remaining"] >= 2:
            return {"tool": "schema"}
        return {"tool": "submit", "sql": self.choose(checked, original, observation)}

    def choose(self, checked, original, observation):
        matches = [h for h in checked if h["observation"].get("matches_example")]
        if matches:
            weak = not any(cell is not None for row in observation['example']['rows'] for cell in row)
            if self.config.get('rank_matches') and (not weak or self.config.get('rank_weak')):
                from ranking import quality
                schema = next((h['observation'] for h in observation['history'] if h['tool']=='schema'),None)
                return max(matches,key=lambda h:quality(h['sql'],observation['task']['question'],observation['example'],schema))['sql']
            return matches[-1]["sql"]
        executable = [h for h in checked if h["observation"].get("ok")]
        return executable[-1]["sql"] if executable else original


def create_agent(checkpoint=None):
    config = json.loads(Path(checkpoint).read_text(encoding="utf-8")) if checkpoint else None
    return RepairAgent(config)
