"""Linear undo/redo history via the command pattern. Pushing a new
command clears the redo stack."""

from dataclasses import dataclass
from typing import Callable


@dataclass
class Command:
    undo: Callable[[], None]
    redo: Callable[[], None]


class UndoManager:
    def __init__(self):
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []

    def push(self, command: Command):
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack:
            return
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

    def redo(self):
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        command.redo()
        self._undo_stack.append(command)

    def clear(self):
        """Call when the underlying data is replaced wholesale (e.g.
        a CSV import)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
