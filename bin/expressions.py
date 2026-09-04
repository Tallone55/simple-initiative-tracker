"""Safe evaluation of arithmetic/dice expressions typed into
integer-only fields (e.g. "12+8", "2d6+5"). Parses to an AST and only
permits a whitelist of node types -- no eval()/exec()."""

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

# Matches "xdy" (e.g. "2d6") or bare "dy" (1dy).
_DICE_PATTERN = re.compile(r"(?<![\w.])(\d*)d(\d+)(?![\w.])", re.IGNORECASE)

_MAX_DICE_COUNT = 10_000
_MAX_DICE_SIDES = 100_000

# GObject's `int` properties are a 32-bit signed gint.
_GINT_MIN = -(2**31)
_GINT_MAX = 2**31 - 1


class ExpressionError(ValueError):
    pass


def _roll_dice(count: int, sides: int) -> int:
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
    def replace(match):
        count_str, sides_str = match.group(1), match.group(2)
        count = int(count_str) if count_str else 1
        sides = int(sides_str)
        return str(_roll_dice(count, sides))

    return _DICE_PATTERN.sub(replace, text)


def evaluate_int_expression(text: str) -> int:
    """Blank/whitespace-only text evaluates to 0. Raises
    ExpressionError for invalid syntax, non-integer results, or
    results outside GObject's gint range."""
    text = text.strip()
    if not text:
        return 0

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

    if not (_GINT_MIN <= result <= _GINT_MAX):
        raise ExpressionError(
            f"{result} is out of range ({_GINT_MIN} to {_GINT_MAX})."
        )

    return result


def _eval_node(node):
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
