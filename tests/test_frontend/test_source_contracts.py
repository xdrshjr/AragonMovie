"""Frontend source contracts.

The repo has no JS test runner installed (no vitest / testing-library), so these
tests assert the *markup contracts* that the UI relies on for accessibility and
for automation. They are cheap and catch the exact regressions reported:

- BUG 10: label / control association in Input + Textarea
- BUG 11: ImageGrid options must be real controls (not bare divs)
- BUG 9: Button must expose a loading text override
- BUG 8: the progress log must use the freshly computed stage
- BUG 13: type labels must replace *all* underscores
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "frontend" / "src"


def read(rel_path: str) -> str:
    path = SRC / rel_path
    assert path.exists(), f"missing frontend file: {path}"
    return path.read_text(encoding="utf-8")


class TestImageGridAccessibility:
    """BUG 11: selectable images must be keyboard- and AT-usable."""

    @pytest.fixture()
    def source(self) -> str:
        return read("components/ui/ImageGrid.tsx")

    def test_tiles_are_buttons_not_divs(self, source):
        assert "<button" in source
        # The old markup was `<div key=... onClick=...>` for each tile
        assert "onClick={() => onSelect(image.id)}" in source
        assert "role=\"option\"" in source

    def test_selection_is_exposed_semantically(self, source):
        assert 'aria-selected={image.selected}' in source
        assert 'role="listbox"' in source

    def test_tiles_are_locatable_by_automation(self, source):
        assert "data-testid={`${testIdPrefix}-${index}`}" in source
        assert "data-selected={image.selected}" in source

    def test_accessible_name_is_not_a_data_url(self, source):
        # BUG 11: alt used to be `Image ${image.id}` where id is a data-URL
        assert "alt={`Image ${image.id}`}" not in source
        assert "alt={optionLabel}" in source
        assert "image.label ??" in source

    def test_keyboard_focus_is_visible(self, source):
        assert "focus-visible:ring" in source

    def test_call_sites_give_labels_and_test_ids(self):
        for step in (
            "components/steps/Step2CharacterImages.tsx",
            "components/steps/Step3SceneImages.tsx",
        ):
            sel = read(step)
            assert "testIdPrefix=" in sel, f"{step} must pass a testIdPrefix"
            assert "label={" in sel, f"{step} must pass an accessible group label"
            assert "label: `" in sel, f"{step} must pass per-tile labels"


class TestLabelAssociation:
    """BUG 10: <label> must be associated with its control."""

    def test_input_associates_label(self):
        source = read("components/ui/Input.tsx")
        assert "htmlFor={inputId}" in source
        assert "id={inputId}" in source
        assert "aria-describedby" in source

    def test_textarea_associates_label(self):
        source = read("components/ui/Textarea.tsx")
        assert "htmlFor={textareaId}" in source
        assert "id={textareaId}" in source
        assert "aria-describedby" in source

    def test_provider_card_secret_field_is_labelled(self):
        """The settings center had the same defect: a <label> without htmlFor."""
        source = read("components/settings/ProviderCard.tsx")
        assert "const fieldId =" in source
        assert "htmlFor={fieldId}" in source
        assert "id={fieldId}" in source
        # the bare, unassociated label must be gone
        assert '<label className="text-sm font-medium text-text-primary">' not in source

    def test_select_accepts_an_id(self):
        source = read("components/ui/ConfigPanel.tsx")
        assert "id?: string;" in source
        assert "id={id}" in source

    def test_new_project_form_uses_labelled_controls(self):
        source = read("app/projects/new/page.tsx")
        assert "<Input" in source
        assert "<Textarea" in source
        assert 'label="Project Name *"' in source
        assert 'label="Description (Optional)"' in source
        # the old hand-rolled label/input pair is gone
        assert '<label className="block text-sm font-medium text-[var(--color-text-secondary)]' not in source


class TestButtonLoadingText:
    """BUG 9: loading text must be configurable instead of hardcoded."""

    def test_button_supports_loading_text(self):
        source = read("components/ui/Button.tsx")
        assert "loadingText" in source
        assert "loadingText ?? 'Loading...'" in source

    def test_steps_use_loading_text(self):
        for step in (
            "components/steps/Step2CharacterImages.tsx",
            "components/steps/Step3SceneImages.tsx",
        ):
            sel = read(step)
            assert 'loadingText="Generating..."' in sel, f"{step} missing loadingText"
            # the previously dead ternary branch must be gone
            assert "<>Generating...</>" not in sel, f"{step} still has the dead branch"


class TestProgressStageLogging:
    """BUG 8: the log must not use the stale closure value."""

    def test_stage_is_computed_once_and_reused(self):
        source = read("components/steps/Step4VideoProgress.tsx")
        assert "export function resolveStage(" in source
        assert "const stage = resolveStage(statusUpdate.progress, isQuickMode);" in source
        assert "${stage}`" in source
        assert "${currentStage}`" not in source


class TestTypeLabel:
    """BUG 13: replace every underscore, not just the first."""

    def test_project_card_uses_replace_all(self):
        source = read("components/ProjectCard.tsx")
        assert "replaceAll('_', ' ')" in source
        assert "replace('_', ' ')" not in source

    def test_project_detail_page_uses_replace_all(self):
        source = read("app/projects/[projectId]/page.tsx")
        assert "replaceAll('_', ' ')" in source
        assert "replace('_', ' ')" not in source
