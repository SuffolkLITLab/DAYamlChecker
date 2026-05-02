from pathlib import Path
from unittest.mock import patch

from dayamlchecker._files import (
    DayamlProjectConfig,
    _collect_dayaml_cli_args,
    _collect_dayaml_ignore_codes,
    _load_dayaml_project_config,
    _normalize_cli_args,
    _normalize_ignore_codes,
)


def test_normalize_ignore_codes_handles_strings_and_invalid_types() -> None:
    assert _normalize_ignore_codes(" e301, e410 , ,c101 ") == frozenset(
        {"E301", "E410", "C101"}
    )
    assert _normalize_ignore_codes(["e101, e102", 123, " c103 "]) == frozenset(
        {"E101", "E102", "C103"}
    )
    assert _normalize_ignore_codes(123) == frozenset()


def test_normalize_cli_args_handles_strings_and_invalid_types() -> None:
    assert _normalize_cli_args('--flag "two words" --count=2') == (
        "--flag",
        "two words",
        "--count=2",
    )
    assert _normalize_cli_args({"not": "supported"}) == ()


def test_load_dayaml_project_config_ignores_non_mapping_dayaml_section(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        "[tool]\n"
        'dayaml = "not-a-table"\n',
        encoding="utf-8",
    )

    config = _load_dayaml_project_config(tmp_path)

    assert config is not None
    assert config.project_root == tmp_path
    assert config.yaml_path == tmp_path / "docassemble"
    assert config.ignore_codes == frozenset()
    assert config.cli_args == ()


def test_load_dayaml_project_config_handles_blank_and_absolute_yaml_paths(
    tmp_path: Path,
) -> None:
    blank_root = tmp_path / "blank"
    blank_root.mkdir()
    (blank_root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        "[tool.dayaml]\n"
        'yaml_path = "   "\n',
        encoding="utf-8",
    )

    blank_config = _load_dayaml_project_config(blank_root)

    assert blank_config is not None
    assert blank_config.yaml_path == blank_root / "docassemble"

    absolute_root = tmp_path / "absolute"
    absolute_root.mkdir()
    absolute_yaml_path = tmp_path / "shared-docassemble"
    (absolute_root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        "[tool.dayaml]\n"
        f'yaml_path = "{absolute_yaml_path}"\n',
        encoding="utf-8",
    )

    absolute_config = _load_dayaml_project_config(absolute_root)

    assert absolute_config is not None
    assert absolute_config.yaml_path == absolute_yaml_path


def test_collect_dayaml_helpers_skip_duplicate_projects(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    nested = project_root / "docassemble" / "pkg" / "data" / "questions"
    nested.mkdir(parents=True)
    first = nested / "first.yml"
    second = nested / "second.yml"
    other_root = tmp_path / "other-project"
    other_nested = other_root / "docassemble" / "pkg" / "data" / "questions"
    other_nested.mkdir(parents=True)
    third = other_nested / "third.yml"
    first.write_text("question: first\n", encoding="utf-8")
    second.write_text("question: second\n", encoding="utf-8")
    third.write_text("question: third\n", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
        "[tool.dayaml]\n"
        'ignore_codes = ["e301", "e410"]\n'
        'args = "--no-url-check --template-url-severity error"\n'
        'check_args = ["--wcag", 123, "--url-check"]\n',
        encoding="utf-8",
    )
    (other_root / "pyproject.toml").write_text(
        '[project]\nname = "other"\nversion = "0.1.0"\n\n'
        "[tool.dayaml]\n"
        'ignore_codes = "e999"\n'
        'args = ["--strict"]\n',
        encoding="utf-8",
    )

    paths = [first, second, third]

    assert _collect_dayaml_ignore_codes(paths) == frozenset({"E301", "E410", "E999"})
    assert _collect_dayaml_cli_args(paths) == (
        "--no-url-check",
        "--template-url-severity",
        "error",
        "--wcag",
        "--url-check",
        "--strict",
    )


def test_collect_dayaml_helpers_continue_after_missing_project_config(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.yml"
    second_path = tmp_path / "second.yml"
    first_path.write_text("question: first\n", encoding="utf-8")
    second_path.write_text("question: second\n", encoding="utf-8")

    missing_project = tmp_path / "missing-project"
    loaded_project = tmp_path / "loaded-project"
    config = DayamlProjectConfig(
        project_root=loaded_project,
        yaml_path=loaded_project / "docassemble",
        ignore_codes=frozenset({"E777"}),
        cli_args=("--from-config",),
    )

    with (
        patch(
            "dayamlchecker._files._find_nearest_pyproject_dir",
            side_effect=[missing_project, loaded_project],
        ),
        patch(
            "dayamlchecker._files._load_dayaml_project_config",
            side_effect=[None, config],
        ),
    ):
        assert _collect_dayaml_ignore_codes([first_path, second_path]) == frozenset(
            {"E777"}
        )

    with (
        patch(
            "dayamlchecker._files._find_nearest_pyproject_dir",
            side_effect=[missing_project, loaded_project],
        ),
        patch(
            "dayamlchecker._files._load_dayaml_project_config",
            side_effect=[None, config],
        ),
    ):
        assert _collect_dayaml_cli_args([first_path, second_path]) == ("--from-config",)
