"""Transparent, untrained structural quality prior for SQL candidate selection.

Scores are hypotheses, never substitutes for official execution feedback. This
module reads no files, task IDs, result cells, or grading data. Use it only as a
tie-breaker among checked public matches or as a candidate-priority adjustment.
"""
import re

import sqlglot
from sqlglot import exp


def _bare(node):
    return node.this if isinstance(node, exp.Alias) else node


def _signature(node):
    node = _bare(node).copy()
    for column in node.find_all(exp.Column):
        column.set("table", None)
        column.set("db", None)
        column.set("catalog", None)
    return re.sub(r"\s+", "", node.sql(dialect="sqlite", normalize=True)).lower()


def _heading(text):
    if not isinstance(text, str) or len(text) > 200:
        return None
    try:
        trees = sqlglot.parse("SELECT " + text, read="sqlite")
        if len(trees) != 1 or not isinstance(trees[0], exp.Select):
            return None
        tree = trees[0]
        if len(tree.expressions) != 1 or any(tree.args.get(key) for key in (
                "from", "joins", "where", "group", "having", "order", "limit")):
            return None
        node = tree.expressions[0]
        if not isinstance(node, (exp.Column, exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
            return None
        if any(isinstance(n, (exp.Literal, exp.Select, exp.Subquery)) for n in node.walk()):
            return None
        return node
    except (sqlglot.errors.SqlglotError, ValueError, RecursionError):
        return None


def _root_nodes(tree, kind):
    return [n for n in tree.find_all(kind) if n.find_ancestor(exp.Select) is tree]


def quality_features(sql, question, example, schema=None):
    """Return fixed, inspectable feature contributions; larger is preferred."""
    try:
        trees = sqlglot.parse(sql, read="sqlite")
        if len(trees) != 1 or not isinstance(trees[0], (exp.Select, exp.SetOperation)):
            return {"invalid": -1000.0}
        tree = trees[0]
    except (sqlglot.errors.SqlglotError, ValueError, RecursionError):
        return {"invalid": -1000.0}
    if any(isinstance(n, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
                          exp.Command, exp.Into)) for n in tree.walk()):
        return {"invalid": -1000.0}
    # A set operation has its output shape from its leftmost SELECT.
    root = tree
    while isinstance(root, exp.SetOperation):
        root = root.this
    if not isinstance(root, exp.Select):
        return {}
    q = str(question).lower()[:4000]
    headings = (example or {}).get("columns", [])
    features = {}
    if headings and not any(isinstance(_bare(x), exp.Star) for x in root.expressions):
        features["projection_width"] = -4.0 * min(4, abs(len(root.expressions) - len(headings)))
        alignment = 0.0
        missing_aggregate = 0.0
        for actual, heading in zip(root.expressions, headings):
            expected = _heading(heading)
            if expected is None:
                continue
            wanted = _signature(expected)
            actual_signature = _signature(actual)
            alias_match = bool(actual.alias) and actual.alias.lower() == str(heading).lower()
            alignment += 1.5 if wanted == actual_signature or alias_match else -1.5
            if isinstance(expected, exp.AggFunc) and not _bare(actual).find(exp.AggFunc):
                missing_aggregate -= 3.0
        features["projection_alignment"] = alignment
        features["projection_aggregation"] = missing_aggregate

    root_aggregates = []
    for aggregate in _root_nodes(root, exp.AggFunc):
        attached = aggregate
        while isinstance(attached.parent, exp.Filter) and attached.parent.this is attached:
            attached = attached.parent
        if not (isinstance(attached.parent, exp.Window) and attached.parent.this is attached):
            root_aggregates.append(aggregate)
    plain_columns = [x for x in root.expressions if isinstance(_bare(x), exp.Column)]
    if root_aggregates and plain_columns and not root.args.get("group"):
        # MIN/MAX with bare columns is legal SQLite; do not impose a ban.
        features["ungrouped_mixed_projection"] = -1.0

    if re.search(r"\b(distinct|unique|different)\b", q):
        if not tree.find(exp.Distinct) and not root.args.get("group") and not isinstance(tree, exp.SetOperation):
            features["requested_distinct"] = -1.5
    if re.search(r"\b(most common|most frequent(?:ly)?|largest number|highest number|greatest number)\b", q):
        order = root.args.get("order")
        aliases = {x.alias.lower(): _bare(x) for x in root.expressions if x.alias}
        if order:
            expressions = []
            for item in order.expressions:
                value = item.this
                if isinstance(value, exp.Column) and not value.table:
                    value = aliases.get(value.name.lower(), value)
                expressions.append(value)
            if not any(x.find(exp.Count) for x in expressions):
                features["frequency_order"] = -2.0
    if re.search(r"\bnever\b", q):
        anti = isinstance(tree, exp.Except)
        for node in tree.find_all(exp.Not):
            anti = anti or isinstance(node.this, exp.Exists) or (
                isinstance(node.this, exp.In) and node.this.args.get("query") is not None)
        anti = anti or any(isinstance(n.this, exp.Column) and isinstance(n.expression, exp.Null)
                          for n in tree.find_all(exp.Is))
        if not anti:
            features["missing_anti_condition"] = -2.0

    # Comparing greater than ANY row is existential (MIN boundary), whereas a
    # greater-than-MAX scalar condition expresses ALL. Only score clear wording.
    existential_high = bool(re.search(
        r"\b(?:after|later than|higher than|greater than|more than|larger than|older than)\s+any\b", q))
    existential_low = bool(re.search(
        r"\b(?:before|earlier than|lower than|less than|smaller than|younger than)\s+any\b", q))
    wrong_boundaries = 0
    for node in tree.walk():
        if not isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE)):
            continue
        value = node.expression
        if not isinstance(value, exp.Subquery):
            continue
        wrong_boundaries += bool(existential_high and isinstance(node, (exp.GT, exp.GTE))
                                 and value.find(exp.Max))
        wrong_boundaries += bool(existential_low and isinstance(node, (exp.LT, exp.LTE))
                                 and value.find(exp.Min))
    if wrong_boundaries:
        features["any_scalar_boundary"] = -2.0 * wrong_boundaries

    # Penalize a directly tautological column join independently of schema.
    tautologies = 0
    for join in root.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            tautologies += sum(isinstance(n.this, exp.Column) and isinstance(n.expression, exp.Column)
                              and n.this.sql(normalize=True) == n.expression.sql(normalize=True)
                              for n in on.find_all(exp.EQ))
    features["tautological_join"] = -5.0 * tautologies

    if schema:
        known = {t["name"].lower(): {c["name"].lower() for c in t.get("columns", [])}
                 for t in schema}
        tables = _root_nodes(root, exp.Table)
        aliases = {t.alias_or_name.lower(): t.name.lower() for t in tables}
        cte_aliases = {node.alias_or_name.lower() for node in tree.find_all(exp.CTE)}
        projection_aliases = {x.alias.lower() for x in root.expressions if x.alias}
        missing_tables = sum(t.name.lower() not in known and t.name.lower() not in cte_aliases
                             for t in tables)
        missing_columns = 0
        for column in _root_nodes(root, exp.Column):
            if column.is_star:
                continue
            name = column.name.lower()
            if not column.table and name in projection_aliases:
                continue
            if column.table:
                table = aliases.get(column.table.lower())
                # Derived-table aliases are deliberately not scored as missing.
                if table in known and name not in known[table]:
                    missing_columns += 1
            elif tables and all(t.name.lower() in known for t in tables):
                missing_columns += not any(name in known[t.name.lower()] for t in tables)
        features["schema_missing_tables"] = -4.0 * min(4, missing_tables)
        features["schema_missing_columns"] = -2.0 * min(4, missing_columns)

    # Tiny complexity tie-breaker; it cannot outweigh structural alignment.
    features["complexity"] = -.01 * min(100, sum(1 for _ in tree.walk()))
    return features


def quality(sql, question, example, schema=None):
    return float(sum(quality_features(sql, question, example, schema).values()))
