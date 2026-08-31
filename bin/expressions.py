"""Safe evaluation of plain arithmetic typed into integer-only fields,
e.g. "12+8", "(20-3)*2", "100//4", "42", or dice notation like "2d6+5".

This deliberately does NOT use eval()/exec() -- those would execute
arbitrary Python from a text field. Instead the text is parsed into an
AST and only a small whitelist of node types (numeric literals, the
standard arithmetic operators, unary sign, and parentheses -- which ast
handles as grouping, not a distinct node type) is permitted to evaluate.
Anything else raises ExpressionError.

Dice notation ("xdy" or bare "dy" meaning 1dy) is resolved with a regex
pass *before* parsing: each dice token is replaced with the literal
integer sum of rolling it, so "2d6+5" becomes e.g. "9+5" and is then
evaluated as ordinary arithmetic -- dice rolls compose naturally with the
rest of an expression, including inside parentheses. This intentionally
avoids pulling in a dedicated dice-notation library: the actual need
here (sum N random integers in a range) doesn't warrant the dependency.
"""

import ast
import operator
import random
import re

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Matches "xdy" (e.g. "2d6") or bare "dy" (e.g. "d20", meaning 1d20). The
# lookbehind/lookahead exclude word characters and '.' immediately
# outside the match, so this only fires on a clean, standalone dice
# token -- not e.g. a 'd' embedded in some other run of characters -- and
# anything left over that isn't a genuine dice token will simply fail to
# parse as an expression afterwards. That's the "filter out false
# positives" behavior: no separate validation pass needed, the normal
# parser rejects whatever doesn't belong.
_DICE_PATTERN = re.compile(r"(?<![\w.])(\d*)d(\d+)(?![\w.])", re.IGNORECASE)

_MAX_DICE_COUNT = 10_000
_MAX_DICE_SIDES = 100_000

# GObject's `int` properties are backed by a 32-bit signed gint.
_GINT_MIN = -(2**31)
_GINT_MAX = 2**31 - 1


class ExpressionError(ValueError):
    """Raised when a typed value isn't a valid integer or arithmetic
    expression, or evaluates to something that can't be an integer."""


def _roll_dice(count: int, sides: int) -> int:
    """Rolls `count` dice of `sides` sides each and returns their sum,
    with sanity bounds against absurd input (e.g. a typo'd huge number)."""
    if sides < 1:
        raise ExpressionError(f"A die must have at least 1 side (got d{sides}).")
    if count < 0:
        raise ExpressionError(f"Dice count cannot be negative (got {count}d{sides}).")
    if count > _MAX_DICE_COUNT or sides > _MAX_DICE_SIDES:
        raise ExpressionError(
            f"{count}d{sides} is unreasonably large "
            f"(max {_MAX_DICE_COUNT} dice, max d{_MAX_DICE_SIDES})."
        )
    return sum(random.randint(1, sides) for _ in range(count))


def _substitute_dice_rolls(text: str) -> str:
    """Replaces every dice-notation token in text with the literal
    integer sum of rolling it, leaving the rest of the text untouched
    for the arithmetic parser to handle afterward."""
    def replace(match):
        count_str, sides_str = match.group(1), match.group(2)
        count = int(count_str) if count_str else 1
        sides = int(sides_str)
        return str(_roll_dice(count, sides))

    return _DICE_PATTERN.sub(replace, text)


def evaluate_int_expression(text: str) -> int:
    """Evaluates text as an integer or arithmetic/dice expression and
    returns the result as an int. Raises ExpressionError for invalid
    syntax, non-integer results, or results outside GObject's gint
    range -- never raises any other exception type, so callers only
    need to catch ExpressionError."""
    text = text.strip()
    if not text:
        raise ExpressionError("Value cannot be empty.")

    text = _substitute_dice_rolls(text)

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"Not a valid number or expression: {text!r}") from e

    try:
        result = _eval_node(tree.body)
    except (TypeError, ZeroDivisionError) as e:
        raise ExpressionError(str(e)) from e

    if isinstance(result, float):
        if not result.is_integer():
            raise ExpressionError(
                f"Expression must resolve to a whole number, got {result}."
            )
        result = int(result)

    result = int(result)

    # CreatureObject's int properties are backed by GObject's 32-bit
    # signed gint. Without this check, an out-of-range result doesn't
    # fail here -- it fails later and much less clearly, as a raw
    # TypeError deep inside PyGObject's property-setting machinery the
    # first time the value is assigned to a CreatureObject property.
    if not (_GINT_MIN <= result <= _GINT_MAX):
        raise ExpressionError(
            f"{result} is out of range ({_GINT_MIN} to {_GINT_MAX})."
        )

    return result


def _eval_node(node):
    """Recursively evaluates one AST node from the whitelist of
    permitted node types (see module docstring); raises ExpressionError
    for anything outside that whitelist."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ExpressionError(f"Unsupported value: {node.value!r}")

    if isinstance(node, ast.BinOp):
        op_func = _ALLOWED_BINOPS.get(type(node.op))
        if op_func is None:
            raise ExpressionError(f"Unsupported operator: {type(node.op).__name__}")
        return op_func(_eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.UnaryOp):
        op_func = _ALLOWED_UNARYOPS.get(type(node.op))
        if op_func is None:
            raise ExpressionError(f"Unsupported operator: {type(node.op).__name__}")
        return op_func(_eval_node(node.operand))

    raise ExpressionError(f"Unsupported expression syntax: {ast.dump(node)}")
