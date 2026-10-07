from pathlib import Path

import pytest

from dayamlchecker import (
    RuntimeOptions,
    find_errors_from_string,
    find_spelling_findings_from_string,
)
from dayamlchecker.messages import (
    MessageId,
    Severity,
    get_message_definition,
    print_github_annotation,
)
from dayamlchecker.spelling import (
    SpellcheckOptions,
    find_spelling_findings,
    spelling_text,
)
from dayamlchecker.style import ParsedInterviewDocument
from dayamlchecker.yaml_structure import main


def spelling(yaml, **options):
    return [
        f
        for f in find_errors_from_string(
            yaml,
            input_file="interview.yml",
            runtime_options=RuntimeOptions(
                spellcheck=SpellcheckOptions(
                    **{k.removeprefix("spellcheck_"): v for k, v in options.items()}
                )
            ),
        )
        if f.message_id
        in {MessageId.SPELLING_POSSIBLE_TYPO, MessageId.SPELLING_COMMON_LEGAL_TYPO}
    ]


def test_public_string_api_returns_only_spelling_warnings():
    findings = find_spelling_findings_from_string("question: Recieve\n")
    assert len(findings) == 1 and findings[0].code == "WG701"


def test_spelling_is_on_by_default_and_reports_locations_without_duplicates():
    yaml = "id: test\nquestion: Adress\nsubquestion: Please recieve teh benefits, not teh letters.\nfield: name\n"
    assert any(f.code == "WG701" for f in find_errors_from_string(yaml))
    assert not any(
        f.code == "WG701"
        for f in find_errors_from_string(
            yaml, runtime_options=RuntimeOptions(spellcheck=None)
        )
    )
    findings = spelling(yaml)
    assert [f.context["word"] for f in findings] == ["Adress", "recieve", "teh"]
    assert [f.line_number for f in findings] == [2, 3, 3]
    assert all(
        f.file_name == "interview.yml" and f.severity == Severity.WARNING
        for f in findings
    )
    assert all(f.context["screen_id"] == "test" for f in findings)


def test_checks_display_labels_and_template_content_but_not_values_or_code():
    yaml = """question: Choose a benefit
fields:
  - Street addres: misspelld_variable
    help: Please recieve the letter.
    choices:
      - Valid label: storred_value
      - label: violance
        value: internnal_value
---
template: message
content: Your lettter is ready.
---
code: |
  internnal_variable = 'misspelld text'
"""
    assert {f.context["word"] for f in spelling(yaml)} == {
        "addres",
        "recieve",
        "violance",
        "lettter",
    }


def test_object_choice_expressions_and_nonlabel_field_keys_are_skipped():
    yaml = """question: Select a person
fields:
  - no label: people
    datatype: object_radio
    choices:
      - requested_guardians if len(requested_guardians.complete_elements()) > 0 else []
  - html: Valid instructions
"""
    assert spelling(yaml) == []


def test_template_markup_urls_and_identifiers_do_not_leak_into_prose():
    raw = """% if user:
${ {'unrecognizabl': {'inner': 'strangeword'}} }
<% PythonUnknwon = 'unrecognizabl' %>
[FILE unrecognizabl.png, 100%]
[:fab-fa-github: Valid label](${ weird_url })
[Helpful link](https://example.org/unrecognizabl)
<span class="unrecognizabl">Valid prose</span>
<script>unrecognizabl</script><style>unrecognizabl</style>
<code>unrecognizabl</code><pre>unrecognizabl</pre>
`unrecognizabl` foo_bar_12
```python
unrecognizabl
```
https://example.org/unrecognizabl unrecognizabl@example.org filexyz.pdf
% endif
"""
    docs = [ParsedInterviewDocument({"question": raw}, raw, 1, 0)]
    assert find_spelling_findings(docs=docs, input_file=None) == []
    assert "Valid prose" in spelling_text(raw)


def test_visible_link_text_and_image_alt_are_checked():
    assert {
        f.context["word"]
        for f in spelling(
            'question: |\n  [Recieve](https://example.org) <img src="weird.png" alt="lettter">\n'
        )
    } == {"Recieve", "lettter"}


@pytest.mark.parametrize(
    "text",
    [
        "Appellee's affidavit of indigency and arrearages",
        "I can't pay. I won’t pay. The tenant's child's benefits.",
        "Pre-filled non-English checkboxes; child(ren) and themself.",
        "Cancelled judgments and wellbeing, ze/zir/zirs.",
        "Ask Quinten Steenhuis about MassHealth and SNAP.",
        "Your café résumé is ready.",
    ],
)
def test_valid_legal_terms_inflections_names_and_markup(text):
    assert spelling(f"question: {text}\n") == []


def test_explicit_translations_and_long_unlabelled_foreign_text_are_skipped():
    assert spelling("language: es\nquestion: Seleccione sus beneficios\n") == []
    assert (
        spelling(
            "question: Seleccione sus beneficios para completar esta solicitud de asistencia jurídica gratuita\n"
        )
        == []
    )
    assert [
        f.context["word"] for f in spelling("language: en-US\nquestion: Recieve\n")
    ] == ["Recieve"]


def test_close_capitalized_typos_are_caught_inside_sentences():
    assert {
        f.context["word"]
        for f in spelling(
            "question: Social Security Adminstration and Plaintiff/Petitoner\n"
        )
    } == {"Adminstration", "Petitoner"}


def test_allowlist_is_case_insensitive_and_does_not_change_other_runs():
    yaml = "question: foobarbaz\n"
    assert spelling(yaml, spellcheck_allowed_words=frozenset({"FOOBARBAZ"})) == []
    assert len(spelling(yaml)) == 1
    assert SpellcheckOptions().allowed_words == frozenset()


@pytest.mark.parametrize("level", list(Severity))
def test_configured_severity_applies_to_all_spelling_rules_only(level):
    findings = find_errors_from_string(
        "question: Recieve the judgement and HIPPA letter\nfields: []\n",
        runtime_options=RuntimeOptions(spellcheck=SpellcheckOptions(severity=level)),
    )
    spelling_findings = [f for f in findings if f.code in {"WG701", "WG702"}]
    assert len(spelling_findings) == 3
    assert all(f.severity == level for f in spelling_findings)
    assert any(
        f.severity == Severity.ERROR and f.code not in {"WG701", "WG702"}
        for f in findings
    )
    assert (
        get_message_definition(MessageId.SPELLING_POSSIBLE_TYPO).severity
        == Severity.WARNING
    )
    assert spelling("question: Recieve\n")[0].severity == Severity.WARNING


@pytest.mark.parametrize("level", list(Severity))
def test_spelling_github_annotations_use_configured_severity(level, capsys):
    finding = spelling("question: HIPPA\n", spellcheck_severity=level)[0]
    print_github_annotation(finding)
    kind = "notice" if level == Severity.INFO else level.value
    output = capsys.readouterr().out
    assert output.startswith(f"::{kind} ")
    assert "title=WG702" in output and "HIPAA" in output


@pytest.mark.parametrize("level,exit_code", [("info", 0), ("warning", 0), ("error", 1)])
def test_cli_default_spellcheck_configured_levels_and_exit_codes(
    tmp_path, capsys, level, exit_code
):
    interview = tmp_path / "spelling.yml"
    interview.write_text(
        "id: test\nquestion: Recieve the judgement and HIPPA letter\nfield: name\n"
    )
    assert (
        main(
            [
                str(interview),
                "--spellcheck-severity",
                level,
                "--no-url-check",
                "--no-docx-accessibility",
                "--no-wcag",
            ]
        )
        == exit_code
    )
    output = capsys.readouterr().out
    label = {"info": "INFO", "warning": "WARN", "error": "ERROR"}[level]
    assert f"{label:<5} [WG701]" in output and f"{label:<5} [WG702]" in output
    assert "judgment" in output and "HIPAA" in output


def test_cli_default_is_warning_and_disable_takes_precedence_over_configuration(
    tmp_path, capsys
):
    interview = tmp_path / "spelling.yml"
    interview.write_text("id: test\nquestion: Recieve HIPPA\nfield: name\n")
    common = [str(interview), "--no-url-check", "--no-docx-accessibility", "--no-wcag"]
    assert main(common) == 0
    assert "WARN  [WG701]" in capsys.readouterr().out
    assert (
        main(
            common
            + [
                "--no-spellcheck",
                "--spellcheck-language",
                "en",
                "--spellcheck-severity",
                "error",
                "--spellcheck-ignore-word",
                "foo",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "[WG701]" not in output and "[WG702]" not in output


def test_cli_info_does_not_count_as_warning_but_warning_limit_does(tmp_path, capsys):
    interview = tmp_path / "spelling.yml"
    interview.write_text("id: test\nquestion: Recieve\nfield: name\n")
    common = [
        str(interview),
        "--no-url-check",
        "--no-docx-accessibility",
        "--no-wcag",
        "--max-warnings",
        "0",
    ]
    assert main(common + ["--spellcheck-severity", "info"]) == 0
    capsys.readouterr()
    assert main(common) == 1
    assert "WARN  [WG701]" in capsys.readouterr().out


def test_invalid_severity_errors_in_api_and_cli(tmp_path, capsys):
    with pytest.raises(ValueError):
        spelling("question: Recieve\n", spellcheck_severity="ignore")
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--spellcheck-severity", "ignore"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize(
    "word,suggestion",
    [
        ("judgement", "judgment"),
        ("Judgement", "Judgment"),
        ("JUDGEMENT", "JUDGMENT"),
        ("judgements", "judgments"),
        ("judgement’s", "judgment's"),
        ("judgement-proof", "judgment-proof"),
        ("HIPPA", "HIPAA"),
        ("hippa", "HIPAA"),
        ("HIPPA's", "HIPAA's"),
        ("HIPPA-compliant", "HIPAA-compliant"),
    ],
)
def test_common_legal_typos_bypass_dictionary_and_case_filters(word, suggestion):
    findings = find_spelling_findings_from_string(f"question: {word}\n")
    assert len(findings) == 1
    finding = findings[0]
    assert finding.message_id == MessageId.SPELLING_COMMON_LEGAL_TYPO
    assert finding.context["suggestion"] == suggestion
    assert suggestion in finding.message


def test_legal_typos_are_deduplicated_and_correct_spellings_are_accepted():
    assert [
        f.context["word"]
        for f in spelling("question: HIPPA HIPPA judgement judgement\n")
    ] == ["HIPPA", "judgement"]
    assert (
        spelling("question: HIPAA Judgment judgments judgmental judgment-proof\n") == []
    )


@pytest.mark.parametrize("level", list(Severity))
def test_legal_typos_respect_suppressions_at_every_severity(level):
    assert (
        spelling(
            "question: HIPPA judgement\n",
            spellcheck_severity=level,
            spellcheck_allowed_words=frozenset({"hippa", "JUDGEMENT"}),
        )
        == []
    )
    assert (
        spelling(
            "question: HIPPA's judgement-proof\n",
            spellcheck_severity=level,
            spellcheck_allowed_words=frozenset({"hippa", "JUDGEMENT"}),
        )
        == []
    )
    assert (
        spelling(
            "question: HIPPA judgement # no-dayc: WG702\n", spellcheck_severity=level
        )
        == []
    )
    assert (
        spelling(
            "question: HIPPA judgement # no-dayc-block: spelling_common_legal_typo\n",
            spellcheck_severity=level,
        )
        == []
    )


@pytest.mark.usefixtures("requires_spanish")
def test_legal_spelling_rules_are_scoped_to_english_and_us_variants(tmp_path):
    assert (
        spelling(
            "question: HIPPA judgement\n",
            spellcheck_languages=("es",),
            spellcheck_allowed_words=frozenset({"judgement"}),
        )
        == []
    )
    prefix = tmp_path / "en_GB"
    prefix.with_suffix(".aff").write_text("SET UTF-8\n")
    prefix.with_suffix(".dic").write_text("1\njudgement\n")
    assert (
        spelling(
            "question: judgement\n",
            spellcheck_languages=("en-GB",),
            spellcheck_dictionaries=(("en-GB", str(prefix)),),
        )
        == []
    )
    assert [
        f.context["suggestion"]
        for f in spelling(
            "question: HIPPA\n",
            spellcheck_languages=("en-GB",),
            spellcheck_dictionaries=(("en-GB", str(prefix)),),
        )
    ] == ["HIPAA"]


@pytest.mark.parametrize(
    "directive", ["# no-dayc: WG701", "# no-dayc-block: spelling_possible_typo"]
)
def test_source_suppressions(directive):
    assert spelling(f"question: Recieve {directive}\n") == []


def test_malformed_yaml_does_not_produce_partial_spelling_warnings():
    assert spelling("question: Recieve\n---\nfields: [\n") == []


def test_cli_custom_wordlist_suppresses_only_listed_words(tmp_path, capsys):
    interview = tmp_path / "test.yml"
    interview.write_text("id: test\nquestion: |\n  foobarbaz lettter\nfield: name\n")
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("# Custom organization\n  # comment\nFOOBARBAZ\n")
    result = main(
        [
            str(interview),
            "--spellcheck-wordlist",
            str(wordlist),
            "--no-url-check",
            "--no-docx-accessibility",
            "--no-wcag",
        ]
    )
    output = capsys.readouterr().out
    assert result == 0
    assert "[WG701]" in output and '"lettter"' in output
    assert '"foobarbaz"' not in output


def test_cli_missing_wordlist_has_clear_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--spellcheck-wordlist", str(tmp_path / "missing")])
    assert exc.value.code == 2
    assert "cannot read spellcheck wordlist" in capsys.readouterr().err


@pytest.mark.usefixtures("requires_spanish")
def test_spanish_inflections_and_accented_typos():
    findings = spelling(
        "question: Seleccione su dirección y beneficios para completar estas soliciitudes\n"
        "subquestion: La direccióón está aquí con los niños y abogados\n",
        spellcheck_languages=("es",),
    )
    assert {f.context["word"] for f in findings} == {"soliciitudes", "direccióón"}


@pytest.mark.usefixtures("requires_spanish")
def test_mixed_languages_within_blocks_and_between_translations():
    yaml = """language: en-US
question: Please complete su solicitud and recieve beneficios
---
language: es-MX
question: Seleccione su dirección para completar esta soliciitud
---
language: fr
question: Cette letttre
"""
    assert [
        f.context["word"] for f in spelling(yaml, spellcheck_languages=("en", "es"))
    ] == ["recieve", "soliciitud"]
    assert {f.context["word"] for f in spelling(yaml)} == {
        "recieve",
        "beneficios",
        "solicitud",
    }


@pytest.mark.usefixtures("requires_spanish")
def test_spanish_default_language_and_templates():
    yaml = """default language: es
---
template: letter
content: La dirección está aquí y contiene una soliciitud
---
language: en
question: Recieve
"""
    assert [f.context["word"] for f in spelling(yaml)] == ["Recieve"]
    assert [
        f.context["word"] for f in spelling(yaml, spellcheck_languages=("es",))
    ] == ["soliciitud"]


@pytest.mark.usefixtures("requires_spanish")
def test_spanish_capitalized_typo_unicode_and_custom_suppression():
    assert [
        f.context["word"]
        for f in spelling("question: Soliciitud\n", spellcheck_languages=("es",))
    ] == ["Soliciitud"]
    yaml = "question: La direccio\u0301n está aquí con direccióón\n"
    assert [
        f.context["word"] for f in spelling(yaml, spellcheck_languages=("es",))
    ] == ["direccióón"]
    assert (
        spelling(
            yaml,
            spellcheck_languages=("es",),
            spellcheck_allowed_words=frozenset({"DIRECCIÓÓN"}),
        )
        == []
    )


@pytest.mark.usefixtures("requires_spanish")
def test_language_selection_and_suppressions_do_not_leak_between_calls():
    yaml = "question: beneficios soliciitud\n"
    assert [
        f.context["word"] for f in spelling(yaml, spellcheck_languages=("en", "es"))
    ] == ["soliciitud"]
    assert (
        spelling(
            yaml,
            spellcheck_languages=("es",),
            spellcheck_allowed_words=frozenset({"soliciitud"}),
        )
        == []
    )
    assert {f.context["word"] for f in spelling(yaml)} == {"beneficios", "soliciitud"}


@pytest.mark.parametrize("languages", [("xx",), (), "es", ("en-GB",)])
def test_invalid_or_unavailable_languages_have_clear_api_errors(languages):
    with pytest.raises(ValueError, match="spellcheck language"):
        spelling("question: Recieve\n", spellcheck_languages=languages)


@pytest.mark.usefixtures("requires_spanish")
def test_language_aliases_and_duplicates():
    assert SpellcheckOptions(languages=("EN_us", "en", "es_US")).languages == (
        "en",
        "es",
    )


@pytest.mark.usefixtures("requires_spanish")
def test_cli_mixed_languages_and_inline_suppressions(tmp_path, capsys):
    interview = tmp_path / "mixed.yml"
    interview.write_text(
        "id: test\nquestion: Please complete su solicitud and recieve beneficios\nsubquestion: lettter\nfield: name\n"
    )
    assert (
        main(
            [
                str(interview),
                "--spellcheck-language",
                "en",
                "--spellcheck-language",
                "es",
                "--spellcheck-ignore-word",
                "RECIEVE",
                "--no-url-check",
                "--no-docx-accessibility",
                "--no-wcag",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "[WG701]" in output and '"lettter"' in output
    assert '"recieve"' not in output and '"beneficios"' not in output


def test_cli_unsupported_language(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--spellcheck-language", "xx"])
    assert exc.value.code == 2
    assert "unsupported spellcheck language" in capsys.readouterr().err


def test_custom_hunspell_dictionary_in_api_and_cli(tmp_path, capsys):
    prefix = tmp_path / "custom"
    prefix.with_suffix(".aff").write_text("SET UTF-8\nSFX S Y 1\nSFX S 0 s .\n")
    prefix.with_suffix(".dic").write_text("1\nfoobarbaz/S\n")
    options = {
        "spellcheck_languages": ("fr",),
        "spellcheck_dictionaries": (("fr", str(prefix)),),
    }
    assert spelling("question: foobarbaz foobarbazs\n", **options) == []
    assert [
        f.context["word"] for f in spelling("question: foobarbazz\n", **options)
    ] == ["foobarbazz"]
    interview = tmp_path / "custom.yml"
    interview.write_text(
        "id: test\nquestion: foobarbaz foobarbazs foobarbazz\nfield: name\n"
    )
    assert (
        main(
            [
                str(interview),
                "--spellcheck-dictionary",
                f"fr={prefix}",
                "--no-url-check",
                "--no-docx-accessibility",
                "--no-wcag",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"foobarbazz"' in output and '"foobarbazs"' not in output


@pytest.mark.parametrize("specification", ["fr", "fr=", "fr=/missing/dictionary"])
def test_cli_invalid_custom_dictionary(tmp_path, capsys, specification):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--spellcheck-dictionary", specification])
    assert exc.value.code == 2
    assert "dictionary" in capsys.readouterr().err


def test_jinja_preprocessing_preserves_spelling_warning_marker():
    findings = spelling(
        "# use jinja\nid: test\nquestion: {{ 'Recieve' }}\nfield: name\n"
    )
    assert len(findings) == 1 and findings[0].rendered_jinja


def test_metadata_is_not_spellchecked():
    assert spelling("""metadata:
  title: Recieve a lettter
  description: misspelld descriptions
  authors:
    - name: Urbana Zafri
      organization: misspelld organization
---
question: Valid question
""") == []


def test_author_names_are_supported_by_declarations_and_scoped_to_proper_names():
    assert spelling("""metadata:
  authors:
    - name: Urbana Zafri
---
question: Urbana wrote this lettter.
""")[0].context["word"] == "lettter"
    assert [f.context["word"] for f in spelling("""metadata:
  authors:
    - name: Urbana Zafri
---
question: urbana
""")] == ["urbana"]


@pytest.mark.parametrize(
    "field",
    [
        "County",
        "Parish",
        "Borough",
        "City",
        "Province",
        "Trial court division",
        "Hearing location preference",
    ],
)
def test_geographic_choices_do_not_require_a_jurisdiction_wordlist(field):
    # Urbana resembles 'urban', so capitalization alone does not suppress it.
    # The schema provides the evidence that these choices are place names.
    yaml = f"""question: Choose a location
fields:
  - {field}: selected_value
    choices:
      - Urbana
      - Ouachita
      - Cuyahoga
      - District Court of Nacogdoches
    help: Please recieve your notice.
"""
    assert [f.context["word"] for f in spelling(yaml)] == ["recieve"]


def test_geographic_context_comes_from_the_variable_even_with_no_label():
    assert spelling("""question: Choose a venue
field: trial_court
choices:
  - Urbana District Court
""") == []


def test_only_geographic_choice_labels_receive_geographic_suppression():
    yaml = """question: County information
fields:
  - County: county
    choices:
      - Urbana
      - I did not recieve a notice
subquestion: Urbana is ready.
"""
    assert {f.context["word"] for f in spelling(yaml)} == {"recieve", "Urbana"}


def test_credit_section_excludes_names_and_keeps_prose_typos():
    yaml = """question: About this interview
subquestion: |
  ### Contributors
  1. Mariah Jennings-Rampsi
  2. Urbana Zafri
  They wrote this lettter.
  ### Instructions
  Please recieve the notice.
"""
    assert [f.context["word"] for f in spelling(yaml)] == ["lettter", "recieve"]


def test_copyright_attributions_exclude_names_and_keep_prose_typos():
    assert [f.context["word"] for f in spelling("""question: About this interview
subquestion: Copyright 2026 Urbana Zafri. Please recieve the notice.
""")] == ["recieve"]


def test_unknown_capitalized_names_are_not_flagged_based_on_sentence_position():
    assert (
        spelling(
            "question: Acura\nsubquestion: Pocketalker is ready. Safelink can help.\n"
        )
        == []
    )
    assert [f.context["word"] for f in spelling("question: Recieve the lettter\n")] == [
        "Recieve",
        "lettter",
    ]


def test_brand_name_typos_are_a_documented_limit_of_the_english_dictionary():
    assert spelling("question: Pick a car\nchoices:\n  - Izuzu\n  - Volkswagon\n") == []


@pytest.mark.parametrize(
    "text", ["Plese recieve this Q&A", "Plese recieve AT&T", "Plese recieve <Word"]
)
def test_text_after_incomplete_html_is_still_checked(text):
    assert spelling_text(text).split()[:2] == ["Plese", "recieve"]
    assert "recieve" in [f.context["word"] for f in spelling(f"question: {text}\n")]


def test_acronyms_do_not_make_english_look_like_another_language():
    yaml = (
        "question: You may get SNAP, TANF, WIC, SSI, SSDI, EITC, LIHEAP or CHIP "
        "if you recieve income.\n"
    )
    assert [f.context["word"] for f in spelling(yaml)] == ["recieve"]


def test_custom_english_dictionary_keeps_english_rules(tmp_path):
    prefix = tmp_path / "en_custom"
    prefix.with_suffix(".aff").write_text("SET UTF-8\n")
    prefix.with_suffix(".dic").write_text("2\ntenant\nlandlord\n")
    options = {"spellcheck_dictionaries": (("en", str(prefix)),)}
    assert spelling("question: tenant's landlord\n", **options) == []


def test_bundled_dictionary_is_not_shadowed_by_working_directory(tmp_path, monkeypatch):
    from dayamlchecker import spelling as spelling_module

    (tmp_path / "en_US.aff").write_text("SET UTF-8\n")
    (tmp_path / "en_US.dic").write_text("1\nzzzz\n")
    monkeypatch.chdir(tmp_path)
    spelling_module._dictionary.cache_clear()
    try:
        assert spelling_module._dictionary("en").lookup("receive")
    finally:
        spelling_module._dictionary.cache_clear()


def test_cli_ignores_spelling_configuration_when_spellcheck_is_off(tmp_path):
    interview = tmp_path / "interview.yml"
    interview.write_text("id: test\nquestion: Hello\nfield: name\n")
    common = ["--no-url-check", "--no-docx-accessibility", "--no-wcag"]
    for extra in (
        ["--spellcheck-language", "xx"],
        ["--spellcheck-dictionary", "fr=/missing/dictionary"],
        ["--spellcheck-wordlist", str(tmp_path / "missing")],
    ):
        assert main([str(interview), "--no-spellcheck", *extra, *common]) == 0


def test_allowed_words_normalize_typographic_apostrophes():
    yaml = "question: Ask Mx. Smith about the o'brienne form.\n"
    assert spelling(yaml) and not spelling(
        yaml, spellcheck_allowed_words=frozenset({" O’Brienne "})
    )
    assert SpellcheckOptions(allowed_words=frozenset({"O’Brienne"})).allowed_words == {
        "o'brienne"
    }


def test_spelling_helper_runs_no_other_checks(monkeypatch):
    from dayamlchecker import yaml_structure

    def fail(*args, **kwargs):
        raise AssertionError("structural checks should not run")

    monkeypatch.setattr(yaml_structure, "_find_interview_level_findings", fail)
    findings = find_spelling_findings_from_string("question: Recieve\n")
    assert [f.context["word"] for f in findings] == ["Recieve"]


def test_style_helper_does_not_run_spellcheck(monkeypatch):
    from dayamlchecker import spelling as spelling_module, yaml_structure

    def fail(*args, **kwargs):
        raise AssertionError("spellcheck should not run")

    monkeypatch.setattr(spelling_module, "find_spelling_findings", fail)
    yaml_structure.find_style_findings_from_string("question: Recieve\n")


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


@pytest.fixture
def fake_remote(tmp_path, monkeypatch):
    """A remote dictionary served from memory, with a counted fetch."""
    import hashlib

    from dayamlchecker import spelling as spelling_module

    files = {".aff": b"SET UTF-8\n", ".dic": b"1\nfoobarbaz\n"}
    remote = spelling_module._RemoteDictionary(
        name="xx_XX",
        base_url="https://example.invalid/",
        sha256={k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
    )
    fetched = []

    def get(url, timeout):
        fetched.append(url)
        return _FakeResponse(files[url[-4:]])

    monkeypatch.setenv("DAYAMLCHECKER_CACHE_DIR", str(tmp_path))
    monkeypatch.setitem(spelling_module._REMOTE_DICTIONARIES, "xx", remote)
    monkeypatch.setattr(spelling_module.requests, "get", get)
    return spelling_module, files, fetched


def test_remote_dictionary_downloads_once_and_reuses_the_cache(fake_remote, tmp_path):
    spelling_module, files, fetched = fake_remote
    prefix = Path(spelling_module._remote_dictionary_prefix("xx"))
    assert prefix.is_relative_to(tmp_path) and len(fetched) == 2
    assert Path(f"{prefix}.dic").read_bytes() == files[".dic"]
    assert spelling_module._remote_dictionary_prefix("xx") == str(prefix)
    assert len(fetched) == 2
    Path(f"{prefix}.dic").write_bytes(b"corrupted")
    spelling_module._remote_dictionary_prefix("xx")
    assert fetched[2:] == ["https://example.invalid/xx_XX.dic"]
    assert Path(f"{prefix}.dic").read_bytes() == files[".dic"]


def test_remote_dictionary_rejects_a_changed_upstream_file(fake_remote, monkeypatch):
    spelling_module, files, _ = fake_remote
    monkeypatch.setattr(
        spelling_module.requests, "get", lambda url, timeout: _FakeResponse(b"x")
    )
    with pytest.raises(ValueError, match="expected SHA-256"):
        spelling_module._remote_dictionary_prefix("xx")


def test_offline_download_failure_is_a_clear_configuration_error(
    fake_remote, monkeypatch, tmp_path, capsys
):
    spelling_module, _, _ = fake_remote

    def offline(url, timeout):
        raise spelling_module.requests.ConnectionError("no network")

    monkeypatch.setattr(spelling_module.requests, "get", offline)
    with pytest.raises(ValueError, match="--spellcheck-dictionary xx=PATH"):
        SpellcheckOptions(languages=("xx",))
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--spellcheck-language", "xx"])
    assert exc.value.code == 2
    assert "cannot download the xx spellcheck dictionary" in capsys.readouterr().err


def test_custom_dictionary_for_a_remote_language_skips_the_download(
    fake_remote, tmp_path
):
    spelling_module, _, fetched = fake_remote
    prefix = tmp_path / "local"
    prefix.with_suffix(".aff").write_text("SET UTF-8\n")
    prefix.with_suffix(".dic").write_text("1\nfoobarbaz\n")
    SpellcheckOptions(languages=("xx",), dictionaries=(("xx", str(prefix)),))
    assert fetched == []
