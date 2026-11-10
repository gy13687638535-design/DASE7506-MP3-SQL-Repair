"""Small, deterministic SQL repairs driven only by current tool feedback.

No benchmark files, task identifiers, result fingerprints, or database connections
are used here. Public column headings guide projection repair; public result
*values* are never copied into SQL. Every returned candidate still needs a check.
"""
from difflib import SequenceMatcher
import re

import sqlglot
from sqlglot import exp


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _bare(expression):
    return expression.this if isinstance(expression, exp.Alias) else expression


def _normalized(expression):
    expression = _bare(expression).copy()
    for column in expression.find_all(exp.Column):
        column.set("table", None)
    return _key(expression.sql(dialect="sqlite"))


def _root_columns(tree):
    return [node for node in tree.find_all(exp.Column)
            if node.find_ancestor(exp.Select) is tree]


def _root_tables(tree):
    return [node for node in tree.find_all(exp.Table)
            if node.find_ancestor(exp.Select) is tree]


def _aggregate_in_scope(expression, tree):
    """Nested scalar subqueries and window functions are not outer aggregates."""
    return any(node.find_ancestor(exp.Select) is tree
               and node.find_ancestor(exp.Window) is None
               for node in expression.find_all(exp.AggFunc))


def _conjuncts(expression):
    if isinstance(expression, exp.And):
        return _conjuncts(expression.this) + _conjuncts(expression.expression)
    if isinstance(expression, exp.Paren) and isinstance(expression.this, exp.And):
        return _conjuncts(expression.this)
    return [expression]


def _and_terms(expressions):
    result = expressions[0].copy()
    for expression in expressions[1:]:
        result = exp.and_(result, expression.copy())
    return result


def _schema_maps(schema):
    tables = {item["name"].lower(): item for item in (schema or [])}
    columns = {name: {column["name"].lower(): column["name"]
                      for column in item.get("columns", [])}
               for name, item in tables.items()}
    return tables, columns


def _projection(tree, example, schema):
    """Align safe expression headings, never assume a heading is executable code."""
    headings = example.get("columns", [])
    if not headings or len(headings) > 32:
        return None
    present = tree.expressions
    tables, columns = _schema_maps(schema)
    available = _root_tables(tree)
    original_columns = _root_columns(tree)
    selected = []
    for heading in headings:
        if not isinstance(heading, str) or len(heading) > 200:
            return None
        heading_key = _key(heading)
        matches = [x for x in present if _normalized(x) == heading_key
                   or _key(x.alias_or_name) == heading_key]
        if matches:
            selected.append(matches[0].copy())
            continue
        try:
            parsed = sqlglot.parse_one("SELECT " + heading, read="sqlite")
        except (sqlglot.errors.SqlglotError, RecursionError):
            return None
        if not isinstance(parsed, exp.Select) or len(parsed.expressions) != 1:
            return None
        expression = parsed.expressions[0]
        if not isinstance(expression, (exp.Column, exp.Count, exp.Sum,
                                       exp.Avg, exp.Min, exp.Max)):
            return None
        # An injected subquery/function/control construct cannot become a repair.
        if any(isinstance(x, (exp.Select, exp.Subquery, exp.Literal, exp.Alias))
               for x in expression.walk()):
            return None
        if any(isinstance(x, exp.Func) and not isinstance(
                x, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max))
               for x in expression.walk()):
            return None
        for column in list(expression.find_all(exp.Column)):
            matches = [x for x in original_columns
                       if x.name.lower() == column.name.lower()]
            if matches:
                column.replace(matches[0].copy())
                continue
            sources = [x for x in available
                       if column.name.lower() in columns.get(x.name.lower(), {})]
            if len(sources) != 1:
                return None
            source = sources[0]
            column.set("table", exp.to_identifier(source.alias_or_name))
            column.set("this", exp.to_identifier(
                columns[source.name.lower()][column.name.lower()]))
        selected.append(expression)
    if [_normalized(x) for x in selected] == [_normalized(x) for x in present]:
        return None
    changed = tree.copy()
    changed.set("expressions", selected)
    return changed


def _schema_repairs(tree, feedback, schema):
    tables, columns = _schema_maps(schema)
    if not tables or sum(1 for _ in tree.find_all(exp.Select)) > 1:
        return []
    message = (feedback.get("error") or {}).get("message", "")
    output = []
    present = _root_tables(tree)
    alias_map = {t.alias_or_name.lower(): t.name.lower() for t in present}
    # Correct only close misspellings; the resulting query is not presumed valid.
    missing_table = re.search(r"no such table:\s*([^\s;]+)", message)
    if missing_table:
        wrong = missing_table.group(1).strip('"`[]')
        close = sorted(tables, key=lambda name: SequenceMatcher(
            None, _key(wrong), _key(name)).ratio(), reverse=True)
        for name in close[:2]:
            if SequenceMatcher(None, _key(wrong), _key(name)).ratio() < .65:
                continue
            changed = tree.copy()
            for table in _root_tables(changed):
                if table.name.lower() == wrong.lower():
                    table.set("this", exp.to_identifier(tables[name]["name"]))
            for col in _root_columns(changed):
                if col.table.lower() == wrong.lower():
                    col.set("table", exp.to_identifier(tables[name]["name"]))
            output.append((changed, "schema_table_spelling", 100.0))
    missing = re.search(r"(?:no such column|ambiguous column name):\s*([^\s;]+)", message)
    if not missing:
        return output
    token = missing.group(1).strip('"`[]')
    qualifier, _, missing_name = token.rpartition(".")
    if not missing_name:
        missing_name = token
    wrong_nodes = [x for x in _root_columns(tree)
                   if x.name.lower() == missing_name.lower()
                   and (not qualifier or x.table.lower() == qualifier.lower())]
    if not wrong_nodes:
        return output
    known = [(t, name) for t in present for name in columns.get(t.name.lower(), {})]
    ranked = []
    for table, name in known:
        score = SequenceMatcher(None, _key(missing_name), _key(name)).ratio()
        if qualifier and qualifier.lower() in alias_map and table.alias_or_name.lower() != qualifier.lower():
            score -= .12
        ranked.append((score, table, name))
    ranked.sort(key=lambda x: -x[0])
    for similarity, source, name in ranked[:2]:
        if similarity < .66:
            continue
        changed = tree.copy()
        for node in _root_columns(changed):
            if node.name.lower() == missing_name.lower() and (
                    not qualifier or node.table.lower() == qualifier.lower()):
                node.set("this", exp.to_identifier(columns[source.name.lower()][name]))
                node.set("table", exp.to_identifier(source.alias_or_name))
        output.append((changed, "schema_column_binding", 100.0 + similarity))
    # A missing field can belong to a table omitted from FROM/JOIN. Consider
    # explicit foreign keys first, then distinctive shared column names.
    present_names = {x.name.lower() for x in present}
    targets = [name for name in tables if name not in present_names
               and missing_name.lower() in columns[name]]
    for target in targets[:4]:
        links = []
        for source in present:
            source_name = source.name.lower()
            if source_name not in tables:
                continue
            for fk in tables[source_name].get("foreign_keys", []):
                if fk["table"].lower() == target:
                    links.append((source, fk["from"], fk["to"], 105.0))
            for fk in tables[target].get("foreign_keys", []):
                if fk["table"].lower() == source_name:
                    links.append((source, fk["to"], fk["from"], 105.0))
            shared = set(columns[source_name]) & set(columns[target])
            for field in sorted(shared):
                if field not in {"name", "type", "id", "description", "date", "year"}:
                    links.append((source, columns[source_name][field],
                                  columns[target][field], 96.0))
        for source, source_field, target_field, priority in links[:3]:
            changed = tree.copy()
            target_name = tables[target]["name"]
            # Qualify fields before introducing a potentially ambiguous join.
            for column in _root_columns(changed):
                if column.name.lower() == missing_name.lower() and (
                        not qualifier or column.table.lower() == qualifier.lower()):
                    column.set("table", exp.to_identifier(target_name))
                    column.set("this", exp.to_identifier(columns[target][missing_name.lower()]))
                elif not column.table:
                    owners = [t for t in present if column.name.lower()
                              in columns.get(t.name.lower(), {})]
                    if len(owners) == 1:
                        column.set("table", exp.to_identifier(owners[0].alias_or_name))
            condition = exp.EQ(this=exp.column(source_field, table=source.alias_or_name),
                               expression=exp.column(target_field, table=target_name))
            joins = list(changed.args.get("joins") or [])
            joins.append(exp.Join(this=exp.to_table(target_name), on=condition))
            changed.set("joins", joins)
            output.append((changed, "schema_missing_join", priority))
    return output


def candidates(sql, question, feedback, example, schema=None):
    """Return (SQL, reason, priority) hypotheses; higher priority is tried first.

    Generation is conservative about parser errors and scope. Distinct/group/
    order edits are hypotheses rather than claims, and never bypass tool checks.
    The caller owns budget enforcement and final-answer selection.
    """
    try:
        parsed = sqlglot.parse(sql, read="sqlite")
    except (sqlglot.errors.SqlglotError, RecursionError, ValueError):
        return []
    if len(parsed) != 1 or not isinstance(parsed[0], (exp.Select, exp.SetOperation)):
        return []
    tree = parsed[0]
    if any(isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create,
                             exp.Drop, exp.Command, exp.Into)) for node in tree.walk()):
        return []
    feedback = feedback or {}
    example = example or {}
    q = str(question).lower()
    generated = []
    if isinstance(tree, exp.Select):
        generated.extend(_schema_repairs(tree, feedback, schema))
        projection = _projection(tree, example, schema)
        if projection is not None:
            generated.append((projection, "public_projection", 92.0))
        simple_projection = all(not _bare(x).find(exp.AggFunc) for x in tree.expressions)
        if simple_projection and not tree.args.get("group"):
            changed = tree.copy()
            if not tree.args.get("distinct"):
                changed.set("distinct", exp.Distinct())
                priority = 82.0 if feedback.get("row_count", 0) > example.get("row_count", 0) else 52.0
                if re.search(r"\b(distinct|different|unique)\b", q):
                    priority += 10
                generated.append((changed, "select_distinct", priority))
            else:
                changed.set("distinct", None)
                generated.append((changed, "remove_distinct", 60.0))
        for count_index, count in enumerate(tree.find_all(exp.Count)):
            if count.find_ancestor(exp.Select) is not tree:
                continue
            argument = count.this
            if isinstance(argument, exp.Distinct) and len(argument.expressions) == 1:
                changed = tree.copy()
                changed_count = list(changed.find_all(exp.Count))[count_index]
                changed_count.set("this", argument.expressions[0].copy())
                generated.append((changed, "remove_count_distinct", 62.0))
            elif isinstance(argument, exp.Column):
                changed = tree.copy()
                changed_count = list(changed.find_all(exp.Count))[count_index]
                changed_count.set("this", exp.Distinct(expressions=[argument.copy()]))
                generated.append((changed, "count_distinct", 65.0))
        # Non-aggregated projections identify plausible grouping keys. This is
        # particularly useful for ordering groups by SUM or COUNT.
        group_keys = [_bare(x).copy() for x in tree.expressions
                      if not _bare(x).find(exp.AggFunc) and not isinstance(_bare(x), exp.Star)]
        order = tree.args.get("order")
        if order and len(order.expressions) == 1:
            ordered = order.expressions[0]
            order_value = ordered.this
            if group_keys and not tree.args.get("group") and _aggregate_in_scope(order_value, tree):
                changed = tree.copy()
                changed.set("group", exp.Group(expressions=group_keys))
                generated.append((changed, "group_for_aggregate_order", 78.0))
            if group_keys and isinstance(order_value, exp.Column) and re.search(
                    r"\b(most|least|fewest|frequent|frequency|maximum|minimum|total)\b", q):
                for aggregate, reason in [(exp.Count(this=exp.Star()), "group_count_order"),
                                          (exp.Sum(this=order_value.copy()), "group_sum_order")]:
                    changed = tree.copy()
                    if not tree.args.get("group"):
                        changed.set("group", exp.Group(expressions=[x.copy() for x in group_keys]))
                    changed.args["order"].expressions[0].set("this", aggregate)
                    generated.append((changed, reason, 66.0))
            direction = None
            if re.search(r"\b(ascending|alphabetical|alphabetically|lowest|smallest|least|fewest|earliest)\b", q):
                direction = False
            elif re.search(r"\b(descending|highest|largest|most|latest|greatest)\b", q):
                direction = True
            if direction is not None and bool(ordered.args.get("desc")) != direction:
                changed = tree.copy()
                changed.args["order"].expressions[0].set("desc", direction)
                changed.args["order"].expressions[0].set("nulls_first", not direction)
                generated.append((changed, "question_order_direction", 76.0))
        explicit_limit = re.search(r"\b(?:top|first)\s+(\d{1,3})\b", q)
        if explicit_limit and 0 < int(explicit_limit.group(1)) <= 100:
            changed = tree.copy()
            changed.set("limit", exp.Limit(expression=exp.Literal.number(explicit_limit.group(1))))
            generated.append((changed, "question_limit", 73.0))
        if tree.args.get("limit") and re.search(r"\b(all|every|each)\b", q) and not re.search(
                r"\b(top|first|highest|lowest|most|least|largest|smallest)\b", q):
            changed = tree.copy()
            changed.set("limit", None)
            generated.append((changed, "remove_unrequested_limit", 68.0))
        where = tree.args.get("where")
        if (where and _aggregate_in_scope(where, tree) and group_keys
                and not where.find(exp.Or)):
            changed = tree.copy()
            terms = _conjuncts(where.this)
            aggregate_terms = [x for x in terms if _aggregate_in_scope(x, tree)]
            row_terms = [x for x in terms if not _aggregate_in_scope(x, tree)]
            changed.set("where", exp.Where(this=_and_terms(row_terms)) if row_terms else None)
            existing = changed.args.get("having")
            condition = _and_terms(aggregate_terms)
            if existing:
                condition = exp.and_(existing.this.copy(), condition)
            changed.set("having", exp.Having(this=condition))
            if not tree.args.get("group"):
                changed.set("group", exp.Group(expressions=group_keys))
            generated.append((changed, "aggregate_filter_to_having", 94.0))
    # All candidates are serialized from a read-only AST; stable deduplication
    # keeps equivalent edits from consuming multiple checks.
    original = tree.sql(dialect="sqlite")
    seen = {original}
    output = []
    for changed, reason, priority in sorted(generated, key=lambda item: -item[2]):
        candidate = changed.sql(dialect="sqlite")
        if candidate in seen or len(candidate.encode("utf-8")) > 16000:
            continue
        seen.add(candidate)
        output.append((candidate, reason, priority))
    return output[:24]
