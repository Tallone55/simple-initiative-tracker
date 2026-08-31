"""Simple linear undo/redo history using the command pattern.

Each undoable action pushes a Command: a pair of no-argument callables,
undo() and redo(), each responsible for both mutating the data AND
refreshing the UI (by calling AppWindow.after_database_mutation from
within the closure) -- this module itself has no GTK dependency and
doesn't know anything about creatures, windows, or widgets.

Undoing pops from the undo stack, calls undo(), and pushes the same
Command onto the redo stack; redoing does the reverse. Pushing a brand
new command clears the redo stack, matching standard editor behavior --
redo history doesn't survive a genuinely new action.

This is a purely linear stack: undo/redo must happen in the order
actions were performed. That's an intentional simplification -- there's
no branching history here.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class Command:
    undo: Callable[[], None]
    redo: Callable[[], None]
    description: str = ""


class UndoManager:
    def __init__(self):
        """Starts with empty undo and redo stacks."""
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []

    def push(self, command: Command):
        """Records a newly-performed action and clears any redo
        history, since redoing no longer makes sense once a new action
        has happened."""
        self._undo_stack.append(command)
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        """Whether there's anything to undo."""
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        """Whether there's anything to redo."""
        return bool(self._redo_stack)

    def undo(self):
        """Reverts the most recent action, if any, and makes it
        available to redo."""
        if not self._undo_stack:
            return
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

    def redo(self):
        """Re-applies the most recently undone action, if any."""
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        command.redo()
        self._undo_stack.append(command)

    def clear(self):
        """Call when the underlying data is replaced wholesale (e.g. a
        CSV import) -- old commands would reference creature objects no
        longer in the store, so the history stops being meaningful."""
        self._undo_stack.clear()
        self._redo_stack.clear()
