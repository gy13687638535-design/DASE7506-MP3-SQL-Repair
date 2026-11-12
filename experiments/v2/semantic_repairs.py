"""Generic compositional repair hypotheses; no benchmark I/O or result literals.

Every proposal needs an official tool check. Scores are proposal priorities,
not correctness probabilities. Only question text, draft AST, public headings,
and tool feedback are consumed.
"""
import re

import sqlglot
from sqlglot import exp

from repairs import _bare, _normalized, _projection, _root_columns, _root_tables


def _local_columns(node, root):
    return [c for c in node.find_all(exp.Column) if c.find_ancestor(exp.Select) is root]


def _alias_expanded_projection(tree, example, schema):
    changed = _projection(tree, example, schema)
    if changed is None:
        return None
    # SQL ordinals refer to the original projection, not its repaired order.
    for clause in ('order', 'group'):
        node = changed.args.get(clause)
        if node is not None:
            for item in list(node.expressions):
                value = item.this if isinstance(item, exp.Ordered) else item
                if (isinstance(value, exp.Literal) and not value.is_string
                        and re.fullmatch(r'[1-9]\d*', value.this)
                        and int(value.this) <= len(tree.expressions)):
                    value.replace(_bare(tree.expressions[int(value.this)-1]).copy())
    aliases = {x.alias.lower(): _bare(x) for x in tree.expressions if x.alias}
    remaining = {x.alias.lower() for x in changed.expressions if x.alias}
    for clause in ('order', 'having', 'group'):
        node = changed.args.get(clause)
        if node is None:
            continue
        for column in list(_local_columns(node, changed)):
            key = column.name.lower()
            if not column.table and key in aliases and key not in remaining:
                column.replace(aliases[key].copy())
    # When public headings require an aggregate absent from the draft, change
    # the aggregate's grouping and matching ORDER BY expression together.
    aggregates = [_bare(x) for x in changed.expressions if isinstance(_bare(x), exp.AggFunc)]
    introduced = [x for x in aggregates if not any(
        _normalized(x) == _normalized(old) for old in tree.expressions)]
    if introduced:
        group = [_bare(x).copy() for x in changed.expressions
                 if not _bare(x).find(exp.AggFunc) and not isinstance(_bare(x), exp.Star)]
        if group and not changed.args.get('group'):
            changed.set('group', exp.Group(expressions=group))
        order = changed.args.get('order')
        if order:
            for ordered in order.expressions:
                for aggregate in introduced:
                    if aggregate.this is not None and _normalized(ordered.this) == _normalized(aggregate.this):
                        ordered.set('this', aggregate.copy())
                        break
    return changed


def _semantic_columns(tree):
    """Columns outside JOIN predicates, including every filtering clause."""
    return [c for c in _root_columns(tree) if not c.find_ancestor(exp.Join)]


def _stem(text):
    return {w.rstrip('s') for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 2}


def _pruned_queries(tree, question):
    """Propose removal of unused join-only tables, never assert equivalence."""
    if sum(1 for _ in tree.find_all(exp.Select)) != 1:
        return []
    joins = tree.args.get('joins') or []
    tables = _root_tables(tree)
    if not joins or len(tables) != len(joins) + 1:
        return []
    # Aggregate count(*) can intentionally count joined rows. It is only pruned
    # when another qualified expression establishes the requested entity.
    semantic = _semantic_columns(tree)
    if not semantic or any(not c.table for c in semantic):
        return []
    used = {c.table.lower() for c in semantic}
    qwords = _stem(question)
    removable = {t.alias_or_name.lower() for t in tables
                 if t.alias_or_name.lower() not in used
                 and not _stem(t.name.replace('_', ' ')).issubset(qwords)}
    out = []
    # Removing a leaf preserves the bindings of every retained JOIN condition.
    for index, join in enumerate(joins):
        alias = join.this.alias_or_name.lower()
        if alias not in removable:
            continue
        others = [j for i, j in enumerate(joins) if i != index]
        if any(c.table.lower() == alias for j in others for c in j.find_all(exp.Column)):
            continue
        changed = tree.copy()
        changed.set('joins', [j.copy() for j in others])
        out.append((changed, 'prune_unused_join_leaf', 89.0))
    # A single referenced table can be the whole intended query, even if the
    # draft chose a different root. Preserve all semantic clauses and aliases.
    if len(used) == 1 and all(t.alias_or_name.lower() in used | removable for t in tables):
        target = next((t for t in tables if t.alias_or_name.lower() in used), None)
        if target is not None:
            changed = tree.copy()
            changed.set('from', exp.From(this=target.copy()))
            changed.set('joins', [])
            out.append((changed, 'prune_join_only_tables', 90.0))
    return out


def _ungroup_global_aggregate(tree, question):
    if (tree.args.get('group') and not tree.args.get('having')
            and all(isinstance(_bare(x), exp.AggFunc) for x in tree.expressions)
            and not re.search(r'\b(each|per|every|group|groups|grouped)\b', question.lower())):
        changed = tree.copy()
        changed.set('group', None)
        return changed
    return None


def _negative_exists(tree, question):
    if not re.search(r'\b(never|without)\b|\bnot\b.{0,30}\bany\b', question.lower()):
        return []
    if sum(1 for _ in tree.find_all(exp.Select)) != 1:
        return []
    where = tree.args.get('where')
    joins = tree.args.get('joins') or []
    if not where or len(joins) != 1 or tree.args.get('group'):
        return []
    predicate = where.this
    if isinstance(predicate, exp.Not) and isinstance(predicate.this, exp.In):
        positive = predicate.this.copy()
    elif isinstance(predicate, exp.NEQ):
        positive = exp.EQ(this=predicate.this.copy(), expression=predicate.expression.copy())
    else:
        return []
    base = tree.args.get('from')
    join = joins[0]
    if not base or not isinstance(base.this, exp.Table) or not isinstance(join.this, exp.Table):
        return []
    if join.args.get('on') is None:
        return []
    base_alias = base.this.alias_or_name.lower()
    join_alias = join.this.alias_or_name.lower()
    if not all(c.table.lower() == base_alias for e in tree.expressions for c in e.find_all(exp.Column)):
        return []
    if not all(c.table.lower() == join_alias for c in predicate.find_all(exp.Column)):
        return []
    # Ensure remaining ORDER clauses do not refer to the removed outer join.
    if tree.args.get('order') and any(c.table.lower() == join_alias
                                    for c in tree.args['order'].find_all(exp.Column)):
        return []
    inner = exp.Select(expressions=[exp.Literal.number(1)])
    inner.set('from', exp.From(this=join.this.copy()))
    inner.set('where', exp.Where(this=exp.and_(join.args['on'].copy(), positive)))
    changed = tree.copy()
    changed.set('joins', [])
    changed.set('where', exp.Where(this=exp.Not(this=exp.Exists(this=inner))))
    return [(changed, 'negative_membership_not_exists', 112.0)]


def _numeric_comparisons(tree, question):
    output = []
    for comparison in tree.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE):
        column, literal = comparison.this, comparison.expression
        if not isinstance(column, exp.Column) or not isinstance(literal, exp.Literal) or not literal.is_string:
            continue
        if not re.fullmatch(r'-?\d+(?:\.\d+)?', literal.this):
            continue
        if not re.search(r'(?<![\w.])' + re.escape(literal.this) + r'(?![\w.])', question):
            continue
        if not re.search(r'age|duration|length|amount|price|quantity|height|weight|speed|rating|score', column.name.lower()):
            continue
        changed = tree.copy()
        for candidate in changed.find_all(type(comparison)):
            if candidate == comparison:
                candidate.set('this', exp.Cast(this=column.copy(), to=exp.DataType.build('REAL')))
                candidate.set('expression', exp.Literal.number(literal.this))
        output.append((changed, 'question_numeric_comparison', 102.0))
    return output


def _quantifier_extreme(tree, question):
    q = question.lower()
    if not re.search(r'\b(after|before|higher|lower|greater|less)\b.{0,20}\bany\b', q):
        return []
    output = []
    for comparison in tree.find_all(exp.GT, exp.GTE, exp.LT, exp.LTE):
        right = comparison.expression
        if not isinstance(right, exp.Subquery) or not isinstance(right.this, exp.Select):
            continue
        inner = right.this
        if len(inner.expressions) != 1:
            continue
        aggregate = inner.expressions[0]
        replacement = None
        if isinstance(comparison, (exp.GT, exp.GTE)) and isinstance(aggregate, exp.Max):
            replacement = exp.Min(this=aggregate.this.copy())
        elif isinstance(comparison, (exp.LT, exp.LTE)) and isinstance(aggregate, exp.Min):
            replacement = exp.Max(this=aggregate.this.copy())
        if replacement is not None:
            changed = tree.copy()
            for node in changed.find_all(type(comparison)):
                if node == comparison:
                    node.expression.this.set('expressions', [replacement.copy()])
            output.append((changed, 'existential_comparison_extreme', 109.0))
    return output


def _question_literal_prefix(tree, question):
    """Recover an omitted field-name prefix only when present in the question."""
    output = []
    for comparison in tree.find_all(exp.EQ):
        column, value = comparison.this, comparison.expression
        if not isinstance(column, exp.Column) or not isinstance(value, exp.Literal) or not value.is_string:
            continue
        field = column.name.replace('_', ' ')
        if (len(field.split()) > 2 or not value.this or len(value.this) > 80
                or not re.search(r'[a-zA-Z]', value.this)
                or re.search(r'\b(name|id|code|number|description)\b', field, re.I)):
            continue
        phrase = re.search(r'\b' + re.escape(field) + r'\s+' + re.escape(value.this) + r'\b', question, re.I)
        if not phrase:
            continue
        changed = tree.copy()
        for node in changed.find_all(exp.EQ):
            if node == comparison:
                node.set('expression', exp.Literal.string(phrase.group(0)))
        output.append((changed, 'question_literal_prefix', 87.0))
    return output


def candidates(sql, question, feedback, example, schema=None):
    try:
        parsed = sqlglot.parse(sql, read='sqlite')
    except (sqlglot.errors.SqlglotError, RecursionError, ValueError):
        return []
    if len(parsed) != 1 or not isinstance(parsed[0], exp.Select):
        return []
    tree = parsed[0]
    if any(isinstance(n, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Command, exp.Into))
           for n in tree.walk()):
        return []
    question = str(question)
    generated = []
    projection = _alias_expanded_projection(tree, example or {}, schema)
    if projection is not None:
        generated.append((projection, 'compositional_projection', 114.0))
    roots = [tree] + ([projection] if projection is not None else [])
    for root in roots:
        generated.extend(_pruned_queries(root, question))
        global_aggregate = _ungroup_global_aggregate(root, question)
        if global_aggregate is not None:
            generated.append((global_aggregate, 'global_aggregate_remove_group', 93.0))
            generated.extend(_pruned_queries(global_aggregate, question))
        generated.extend(_negative_exists(root, question))
        generated.extend(_numeric_comparisons(root, question))
        generated.extend(_quantifier_extreme(root, question))
        generated.extend(_question_literal_prefix(root, question))
    seen = {tree.sql(dialect='sqlite', normalize=True)}
    result = []
    for changed, reason, priority in sorted(generated, key=lambda row: -row[2]):
        rendered = changed.sql(dialect='sqlite')
        key = changed.sql(dialect='sqlite', normalize=True)
        if key not in seen and len(rendered.encode('utf8')) <= 16000:
            result.append((rendered, reason, priority))
            seen.add(key)
    return result[:24]
