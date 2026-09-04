"""Modal window for editing a creature's full 5e stat block: the six
ability scores, proficiency bonus, to-hit bonus, and per-save/skill
proficiency level + advantage. Opened two ways:

- The crossed-swords column button, for an existing creature --
  on_committed writes straight back onto that creature_obj.
- The "Edit Stats" button in Add Creature, 5e Combat mode only --
  edits a staged stats dict applied to every creature in that batch.

initial_stats/the dict on_committed receives both use this shape:
    {"strength": int, "dexterity": int, "constitution": int,
     "intelligence": int, "wisdom": int, "charisma": int,
     "proficiency_bonus": int, "save_skill_pattern": int,
     "to_hit_bonus": int}

Layout: one row per ability, each with its own score entry, saving
throw, and however many skills it governs. Proficiency Bonus and
To-Hit Bonus sit in their own row above, since neither belongs to any
one ability.
"""

from gi.repository import Gtk

from models import (
    ABILITIES, ABILITY_ABBREVIATIONS, SKILLS_BY_ABILITY,
    ability_modifier, position_index, encode_pattern, decode_pattern,
)
from expressions import evaluate_int_expression, ExpressionError

STATS_DIALOG_TITLE = "Edit Stats"

# A blank ability score is treated as 10 (modifier +0) for live
# display only; storage still keeps 0 ("not set").
_ASSUMED_SCORE_WHEN_BLANK = 10

# Skill proficiency toggle labels, cycled 0/1/2 on each click.
_PROF_LEVEL_LABELS = ["\u2013", "Prof.", "Expert."]


def _format_modifier(mod):
    return f"+{mod}" if mod >= 0 else str(mod)


def open_creature_stats_dialog(parent, initial_stats, on_committed):
    """on_committed(new_stats: dict) is called after a successful
    Update, once the window has already been destroyed."""
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

    # -- proficiency bonus + to-hit bonus ------------------------------------------------

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

    # -- the combined table: one bordered row per ability ------------------------------------------------

    proficiency_levels, advantages = decode_pattern(initial_stats.get("save_skill_pattern", 0))

    rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    ability_entries = {}
    total_labels = {}  # ("save", ability) or ("skill", name) -> Gtk.Label
    save_prof_checks = {}
    save_adv_checks = {}
    skill_prof_buttons = {}  # skill name -> Gtk.Button (own .prof_level attr)
    skill_adv_checks = {}

    # Fixed widths so every block of a given type lines up in a
    # column regardless of its own content.
    _ABILITY_BLOCK_WIDTH = 56
    _SAVE_BLOCK_WIDTH = 150
    _SKILL_BLOCK_WIDTH = 150
    _MAX_SKILLS_PER_ROW = max(len(skills) for skills in SKILLS_BY_ABILITY.values())
    _CHECK_WIDTH = 62

    def _section_separator():
        return Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_top=2, margin_bottom=2)

    def _labeled_block(label_text, controls_row, width, expand_controls=False, margin_end=5):
        """Wraps a label and its controls in a fixed-width box.
        controls_row defaults to left-justified/non-expanding, so
        columns of the same block type line up across rows;
        expand_controls=True lets it fill the block instead (used
        only by the ability-score entry, which centers itself via
        flanking spacers). margin_end defaults to 5 but is reduced to
        0 for the ability block to keep the vertical separator
        visually balanced."""
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=1,
            margin_top=3, margin_bottom=3, margin_start=5, margin_end=margin_end,
        )
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
        """Blank placeholder the width of a skill block, so rows with
        fewer skills still match the widest row's overall length."""
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

        # Three-state proficiency as one cyclable toggle button
        # (None -> Prof. -> Expert.), state tracked as .prof_level.
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
        entry.set_valign(Gtk.Align.CENTER)
        entry.set_size_request(30, -1)
        # Centered via two equal-hexpand flanking spacers, which
        # split any surplus width evenly regardless of the entry's
        # own rendered size.
        entry.set_halign(Gtk.Align.FILL)
        entry.set_hexpand(False)
        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        left_spacer = Gtk.Box(hexpand=True)
        right_spacer = Gtk.Box(hexpand=True)
        entry_row.append(left_spacer)
        entry_row.append(entry)
        entry_row.append(right_spacer)
        score = initial_stats.get(ability, 0)
        entry.set_text(str(score) if score else "")
        ability_entries[ability] = entry
        row_card.append(_labeled_block(
            ABILITY_ABBREVIATIONS[ability], entry_row, _ABILITY_BLOCK_WIDTH,
            expand_controls=True, margin_end=0,
        ))

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
