"""Modal window for editing a creature's full 5e stat block: the six
ability scores, proficiency bonus, to-hit bonus, and per-save/skill
proficiency level + advantage. Opened two ways:

- The crossed-swords column button (column_factory.py/window.py),
  for an existing creature -- on_committed writes straight back onto
  that creature_obj.
- The "Edit Stats" button in Add Creature, 5e Combat mode only
  (creature_dialogs.py) -- edits a *staged* stats dict that then gets
  applied identically to every creature in that bulk-add batch, not
  any specific creature_obj yet.

Both cases share the exact same window/logic here; only what
on_committed does with the result differs. initial_stats/the dict
on_committed receives both use this shape:
    {"strength": int, "dexterity": int, "constitution": int,
     "intelligence": int, "wisdom": int, "charisma": int,
     "proficiency_bonus": int, "save_skill_pattern": int,
     "to_hit_bonus": int}

Layout: one combined table, one row per ability -- the ability's own
score entry is that row's first column, its saving throw next, then
however many skills it governs (Constitution: none; Intelligence/
Wisdom: five, the most of any ability) filling out the rest of the
row. Proficiency Bonus and To-Hit Bonus sit in their own small row
above the table, since neither belongs to any one ability.
"""

from gi.repository import Gtk

from models import (
    ABILITIES, ABILITY_ABBREVIATIONS, SKILLS_BY_ABILITY,
    ability_modifier, position_index, encode_pattern, decode_pattern,
)
from expressions import evaluate_int_expression, ExpressionError

STATS_DIALOG_TITLE = "Edit Stats"

# A blank ability score field is treated as an assumed 10 (modifier
# +0) for every live calculation in this window, rather than as 0
# (modifier -5, the "not set" sentinel used for storage/every other
# purpose elsewhere in this app) -- an actually-entered 0 is still a
# real, valid score and keeps its real -5 modifier; only a genuinely
# empty field gets this substitution.
_ASSUMED_SCORE_WHEN_BLANK = 10

# Proficiency-level toggle button labels, index 0/1/2 -- cycles on
# each click. "Expert." per spec's own abbreviation of Expertise.
_PROF_LEVEL_LABELS = ["\u2013", "Prof.", "Expert."]  # en dash for "none"


def _format_modifier(mod):
    return f"+{mod}" if mod >= 0 else str(mod)


def open_creature_stats_dialog(parent, initial_stats, on_committed):
    """on_committed(new_stats: dict) is called after a successful
    Update, once the window has already been destroyed. See module
    docstring for the dict shape both directions use."""
    window = Gtk.Window(title=STATS_DIALOG_TITLE)
    window.set_modal(True)
    window.set_transient_for(parent)
    window.set_default_size(1350, 680)

    outer_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    root = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=6,
        margin_top=8, margin_bottom=8, margin_start=8, margin_end=8,
    )
    outer_scroller.set_child(root)
    window.set_child(outer_scroller)

    # -- proficiency bonus + to-hit bonus (not tied to any one ability) ------------------------------------------------

    top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    prof_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    prof_box.append(Gtk.Label(label="Prof. Bonus", xalign=0))
    prof_entry = Gtk.Entry(width_chars=4, input_purpose=Gtk.InputPurpose.NUMBER, valign=Gtk.Align.CENTER)
    prof_value = initial_stats.get("proficiency_bonus", 0)
    prof_entry.set_text(str(prof_value) if prof_value else "")
    prof_box.append(prof_entry)
    top_row.append(prof_box)

    to_hit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    to_hit_box.append(Gtk.Label(label="To-Hit Bonus", xalign=0))
    to_hit_entry = Gtk.Entry(width_chars=4, input_purpose=Gtk.InputPurpose.NUMBER, valign=Gtk.Align.CENTER)
    to_hit_value = initial_stats.get("to_hit_bonus", 0)
    to_hit_entry.set_text(str(to_hit_value) if to_hit_value else "")
    to_hit_box.append(to_hit_entry)
    top_row.append(to_hit_box)

    root.append(top_row)
    root.append(Gtk.Separator())

    # -- the combined table: one bordered "card" row per ability ------------------------------------------------

    proficiency_levels, advantages = decode_pattern(initial_stats.get("save_skill_pattern", 0))

    rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    ability_entries = {}
    # Every control that needs to react to a change elsewhere (an
    # ability score, Proficiency Bonus, or any toggle) is collected
    # here so one shared recompute() can walk all of it, rather than
    # each block managing its own isolated refresh.
    total_labels = {}  # ("save", ability) or ("skill", name) -> Gtk.Label
    save_prof_checks = {}
    save_adv_checks = {}
    skill_prof_buttons = {}  # skill name -> Gtk.Button (own .prof_level attr)
    skill_adv_checks = {}

    # Fixed widths so every instance of a given block type -- every
    # ability entry, every Save block, every skill block -- is
    # identical regardless of its own content, which is what actually
    # makes the ability/Save columns line up vertically down the left
    # side of the table (previously each block's width came from its
    # own natural content size, so e.g. "Con" being narrower than
    # "Str" -- or a two-digit save total vs. a one-digit one -- could
    # shift where the Save column started, row to row).
    # Matches the ability-score entry's own natural width (see its
    # construction site for how that 42px figure was measured) --
    # not a few extra pixels of "breathing room" like the other block
    # widths get. Any surplus here has to be distributed by the
    # flanking spacers that center the entry (see its own comment),
    # and that surplus was exactly what kept leaving a visibly larger
    # gap on the entry's side of the vertical separator than the
    # Save block's side had to match -- confirmed directly, and not
    # fixed by simply shrinking the surplus rather than removing it,
    # since any nonzero surplus still has *some* width to contribute
    # asymmetrically. Sized to leave essentially none.
    _ABILITY_BLOCK_WIDTH = 42
    _SAVE_BLOCK_WIDTH = 150
    _SKILL_BLOCK_WIDTH = 150
    _MAX_SKILLS_PER_ROW = max(len(skills) for skills in SKILLS_BY_ABILITY.values())
    # A standardized width for every Prof./Adv. checkbox too, for the
    # same reason -- their label text never varies ("Prof." is always
    # "Prof.", "Adv." is always "Adv."), so their natural width was
    # already consistent in practice, but an explicit size here means
    # that's guaranteed rather than incidental.
    _CHECK_WIDTH = 62

    def _section_separator():
        return Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_top=2, margin_bottom=2)

    def _labeled_block(label_text, controls_row, width, expand_controls=False):
        """Wraps one property's label and controls (a base ability
        score, Save, or one skill) in its own invisible box with
        standardized padding and a fixed width -- every block of the
        same kind (every skill block, every Save block, ...) gets the
        same width regardless of how wide its own content happens to
        be, which is what keeps every row the same overall length and
        every column starting at the same position.

        controls_row defaults to left-justified and non-expanding,
        anchored to the same fixed offset from the block's own left
        edge on every row -- that's what keeps e.g. every Save row's
        checkboxes lined up in a straight column regardless of a
        neighboring row's different number of skills (centering
        multi-widget controls_rows was exactly what broke that column
        alignment before: each row centered independently against its
        own differing natural width instead of sharing one fixed
        reference point). expand_controls=True opts out of that for
        controls_row itself (letting it fill the block's full width)
        -- used for the one controls_row built to center *itself*
        within whatever width it's given (the base ability score
        entry, flanked by two equal-weight spacers -- see its own
        construction site for why that, and not a fixed pixel
        offset, is what actually centers reliably).

        The label above it is different: titles aren't compared
        against each other the way a column of entries is, so there's
        no alignment hazard in letting it expand and center -- and a
        centered title reads better sitting over the block as a
        whole. hexpand=True + halign=CENTER here is scoped to just
        this Label."""
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=1,
            margin_top=3, margin_bottom=3, margin_start=5, margin_end=5,
        )
        # Explicit, not left to GTK's own default: a container with no
        # hexpand of its own set implicitly computes one from whether
        # *any* child requests it -- and since the label below does
        # (hexpand=True, so its own text can center), leaving this box
        # unset would have let that quietly propagate upward, giving
        # this whole block extra width from row_card's leftover space
        # (which varies row to row, since rows have different numbers
        # of skill blocks competing for it) instead of staying at
        # exactly the fixed width passed in -- confirmed the hard way,
        # this was exactly what pulled the Save blocks' own controls
        # out of column alignment again despite controls_row's own
        # halign/hexpand being untouched.
        box.set_hexpand(False)
        box.set_size_request(width, -1)
        label = Gtk.Label(
            label=label_text, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            hexpand=True, css_classes=["dim-label"],
        )
        if expand_controls:
            controls_row.set_hexpand(True)
        else:
            controls_row.set_halign(Gtk.Align.START)
            controls_row.set_hexpand(False)
        controls_row.set_valign(Gtk.Align.CENTER)
        box.append(label)
        box.append(controls_row)
        return box

    def _empty_skill_slot():
        """A blank placeholder the exact width of a real skill block
        -- used to pad out ability rows that govern fewer than
        _MAX_SKILLS_PER_ROW skills (e.g. Strength's one, versus
        Intelligence/Wisdom's five each), so every row is the same
        overall length regardless of how many skills it actually has,
        rather than trailing off early."""
        placeholder = Gtk.Box()
        placeholder.set_size_request(_SKILL_BLOCK_WIDTH, -1)
        return placeholder

    def _build_save_block(ability):
        idx = position_index("save", ability)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        total_label = Gtk.Label(label="+0", width_chars=3, xalign=1, valign=Gtk.Align.CENTER)
        row.append(total_label)
        total_labels[("save", ability)] = total_label

        prof_check = Gtk.CheckButton(label="Prof.", valign=Gtk.Align.CENTER, hexpand=False)
        prof_check.set_size_request(_CHECK_WIDTH, -1)
        prof_check.set_active(proficiency_levels[idx] >= 1)
        row.append(prof_check)
        save_prof_checks[ability] = prof_check

        adv_check = Gtk.CheckButton(label="Adv.", valign=Gtk.Align.CENTER, hexpand=False)
        adv_check.set_size_request(_CHECK_WIDTH, -1)
        adv_check.set_active(advantages[idx])
        row.append(adv_check)
        save_adv_checks[ability] = adv_check

        return _labeled_block("Save", row, _SAVE_BLOCK_WIDTH)

    def _build_skill_block(skill_name):
        idx = position_index("skill", skill_name)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        total_label = Gtk.Label(label="+0", width_chars=3, xalign=1, valign=Gtk.Align.CENTER)
        row.append(total_label)
        total_labels[("skill", skill_name)] = total_label

        # Three-state proficiency as a single cyclable toggle button
        # (None -> Prof. -> Expert. -> None on each click) rather than
        # a group of three linked radio buttons -- state is tracked
        # directly on the button as .prof_level. A fixed size request,
        # wide enough for "Expert." (the longest of the three labels),
        # keeps the button's own width constant across all three
        # states instead of growing/shrinking as its label changes --
        # set once here, not recomputed on click, so it can't drift.
        level = proficiency_levels[idx]
        toggle = Gtk.Button(label=_PROF_LEVEL_LABELS[level])
        toggle.prof_level = level
        toggle.set_size_request(84, -1)
        toggle.set_hexpand(False)
        toggle.set_valign(Gtk.Align.CENTER)

        def on_toggle_clicked(button):
            button.prof_level = (button.prof_level + 1) % 3
            button.set_label(_PROF_LEVEL_LABELS[button.prof_level])
            recompute()

        toggle.connect("clicked", on_toggle_clicked)
        row.append(toggle)
        skill_prof_buttons[skill_name] = toggle

        adv_check = Gtk.CheckButton(label="Adv.", valign=Gtk.Align.CENTER, hexpand=False)
        adv_check.set_size_request(_CHECK_WIDTH, -1)
        adv_check.set_active(advantages[idx])
        row.append(adv_check)
        skill_adv_checks[skill_name] = adv_check

        return _labeled_block(skill_name, row, _SKILL_BLOCK_WIDTH)

    for ability in ABILITIES:
        row_card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
            margin_top=3, margin_bottom=3, margin_start=6, margin_end=6,
        )
        row_card.add_css_class("stat-row")

        entry = Gtk.Entry(width_chars=1, max_width_chars=3, input_purpose=Gtk.InputPurpose.NUMBER)
        # Explicit, not left to GTK's default: a bare Gtk.Entry's own
        # *natural* width (as opposed to the minimum width_chars/
        # size_request govern) defaults to a large, fixed value from
        # the theme regardless of width_chars -- confirmed directly,
        # a bare entry with nothing else applied came out to 168px
        # natural width. max_width_chars is what actually constrains
        # that down to something reasonable; without it, this entry
        # was claiming its full 168px of natural width in any row
        # with enough slack to grant it (Str's row, with only one
        # skill competing for space), which was the real cause of a
        # cascade of symptoms that looked like a centering-mechanism
        # bug at first: the whole block ballooning past its intended
        # 70px, and the entry's own centered position landing a few
        # pixels off from its title above -- both were really just
        # this unconstrained natural width showing up in different
        # ways depending on what alignment was being tried at the
        # time. This entry centers itself via two flanking spacers
        # (see below), passed through _labeled_block with
        # expand_controls=True so the flanking row can actually use
        # the block's full width to work with.
        entry.set_valign(Gtk.Align.CENTER)
        # A width floor, not just width_chars/max_width_chars: those
        # only set the entry's *preferred* width, and a row with five
        # skill blocks crowding it for space (Int, Wis) can still
        # squeeze it narrower than that when the window itself isn't
        # wide enough -- confirmed the data itself stays correct
        # either way (a squeezed entry showing "1" of "12" is a
        # rendering artifact, not lost text), but a hard minimum here
        # means a 2-digit score is never visually clipped regardless
        # of how much space neighboring skills are competing for.
        # valign=CENTER above is the height-side counterpart: without
        # it, this was the one widget in the whole row with no
        # sibling of its own to compact against, so it defaulted to
        # GTK_ALIGN_FILL and stretched to match the row's tallest
        # neighbor instead of sitting at its own natural, compact
        # height like everything else.
        entry.set_size_request(30, -1)
        # Flanked by two equal-hexpand spacers, not halign=CENTER on
        # the entry directly (nor, before that, hand-computed
        # margin_start/margin_end values) -- both of those were tried
        # first and both turned out to depend on the entry's own
        # natural width being some specific, predictable value, which
        # is exactly what doesn't hold reliably across different
        # systems: real screenshots on an actual machine (both with
        # blank fields and with every field filled in) showed a
        # clear, consistent left-bias that plain halign=CENTER in
        # this sandbox didn't reproduce the same way, meaning neither
        # approach was ever really portable, just coincidentally
        # close in whichever one environment it was last tuned
        # against. Two spacers of literally identical, hexpand=True
        # priority on either side of a non-expanding entry removes
        # that dependency entirely: whatever surplus width the block
        # has beyond the entry's own natural size, GTK's box layout
        # splits it equally between two equal-priority hexpand
        # children by definition, not by any measurement of what the
        # entry's own rendered width happens to be on this particular
        # system. That's a property of how GTK's box allocation
        # itself works, not of this font, this theme, or this
        # screen -- which is what should actually make it hold up
        # anywhere, rather than needing yet another number tuned to
        # yet another environment.
        entry.set_halign(Gtk.Align.FILL)
        entry.set_hexpand(False)
        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        left_spacer = Gtk.Box(hexpand=True)
        right_spacer = Gtk.Box(hexpand=True)
        entry_row.append(left_spacer)
        entry_row.append(entry)
        entry_row.append(right_spacer)
        score = initial_stats.get(ability, 0)
        entry.set_text(str(score) if score else "")
        ability_entries[ability] = entry
        row_card.append(_labeled_block(ABILITY_ABBREVIATIONS[ability], entry_row, _ABILITY_BLOCK_WIDTH, expand_controls=True))

        row_card.append(_section_separator())
        row_card.append(_build_save_block(ability))
        row_card.append(_section_separator())

        skills_section = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        skills = SKILLS_BY_ABILITY[ability]
        for skill_name in skills:
            skills_section.append(_build_skill_block(skill_name))
        for _ in range(_MAX_SKILLS_PER_ROW - len(skills)):
            skills_section.append(_empty_skill_slot())
        row_card.append(skills_section)

        rows_box.append(row_card)

    root.append(rows_box)

    # -- live total recompute ------------------------------------------------
    # Reacts to every ability-score entry, Proficiency Bonus, and
    # every proficiency control, so the displayed totals always
    # reflect the form's current state, not just what was there when
    # the window opened. Per spec, only the combined total is ever
    # shown -- there's no separate "raw modifier" label anywhere in
    # this window to also keep in sync.

    def _current_score(ability):
        text = ability_entries[ability].get_text().strip()
        if not text:
            return _ASSUMED_SCORE_WHEN_BLANK
        try:
            return evaluate_int_expression(text)
        except ExpressionError:
            return _ASSUMED_SCORE_WHEN_BLANK

    def _current_prof_bonus():
        try:
            return evaluate_int_expression(prof_entry.get_text())
        except ExpressionError:
            return 0

    def recompute(*_args):
        prof_bonus = _current_prof_bonus()
        for ability in ABILITIES:
            mod = ability_modifier(_current_score(ability))

            save_total = mod + (prof_bonus if save_prof_checks[ability].get_active() else 0)
            total_labels[("save", ability)].set_label(_format_modifier(save_total))

            for skill_name in SKILLS_BY_ABILITY[ability]:
                level = skill_prof_buttons[skill_name].prof_level
                skill_total = mod + prof_bonus * level
                total_labels[("skill", skill_name)].set_label(_format_modifier(skill_total))

    for entry in (*ability_entries.values(), prof_entry):
        entry.connect("changed", recompute)
    for ability in ABILITIES:
        save_prof_checks[ability].connect("toggled", recompute)
    recompute()

    # -- buttons ------------------------------------------------

    error_label = Gtk.Label(visible=False, wrap=True, xalign=0, css_classes=["error"])
    root.append(error_label)

    button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.END)
    cancel_button = Gtk.Button(label="Cancel")
    update_button = Gtk.Button(label="Update", receives_default=True, css_classes=["suggested-action"])
    button_box.append(cancel_button)
    button_box.append(update_button)
    root.append(button_box)

    def on_update(_button):
        try:
            # Storage keeps 0 ("not set") for a field left blank --
            # the _ASSUMED_SCORE_WHEN_BLANK substitution above is only
            # ever used for this window's own live display, not for
            # what actually gets saved.
            new_stats = {ability: evaluate_int_expression(ability_entries[ability].get_text()) for ability in ABILITIES}
            new_stats["proficiency_bonus"] = evaluate_int_expression(prof_entry.get_text())
            new_stats["to_hit_bonus"] = evaluate_int_expression(to_hit_entry.get_text())
        except ExpressionError:
            error_label.set_text(
                "Ability scores, Proficiency Bonus, and To-Hit Bonus must be whole numbers or expressions."
            )
            error_label.set_visible(True)
            return

        levels = [0] * len(proficiency_levels)
        advs = [False] * len(advantages)
        for ability in ABILITIES:
            idx = position_index("save", ability)
            levels[idx] = 1 if save_prof_checks[ability].get_active() else 0
            advs[idx] = save_adv_checks[ability].get_active()
            for skill_name in SKILLS_BY_ABILITY[ability]:
                skill_idx = position_index("skill", skill_name)
                levels[skill_idx] = skill_prof_buttons[skill_name].prof_level
                advs[skill_idx] = skill_adv_checks[skill_name].get_active()
        new_stats["save_skill_pattern"] = encode_pattern(levels, advs)

        window.destroy()
        on_committed(new_stats)

    def on_cancel(_button):
        window.destroy()

    update_button.connect("clicked", on_update)
    cancel_button.connect("clicked", on_cancel)
    window.present()
