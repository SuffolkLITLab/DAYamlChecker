# DAYamlChecker

An LSP for Docassemble YAML Interviews

## How to run

```bash
pip install .
python3 -m dayamlchecker `find . -name "*.yml" -path "*/questions/*" snot -path "*/.venv/*" -not -path "*/build/*"` # i.e. a space separated list of files
```

## WCAG checks

The checker includes WCAG-style checks for clear static accessibility failures in interview source. These checks run by default; use `--no-wcag` to disable them.

```bash
python3 -m dayamlchecker path/to/interview.yml          # WCAG checks on (default)
python3 -m dayamlchecker --no-wcag path/to/interview.yml  # WCAG checks off
python3 -m dayamlchecker --accessibility-error-on-widget combobox path/to/interview.yml  # opt into combobox failures
```

Some accessibility checks are behind runtime options while the rules are still being evaluated. Right now `combobox` failures are default-off and can be enabled with `--accessibility-error-on-widget combobox`.

## Style checks

Assembly Line style checks are opt-in. Enable them with `--style` to run deterministic style findings ported from ALLinter without duplicating the checker’s existing YAML, accessibility, or URL coverage.

```bash
python3 -m dayamlchecker --style --no-url-check path/to/interview.yml
python3 -m dayamlchecker --style-llm --openai-api-key "$OPENAI_API_KEY" path/to/interview.yml
OPENAI_BASE_URL=https://api.openai.com/v1 OPENAI_API_KEY=... python3 -m dayamlchecker --style-llm path/to/interview.yml
```

`--style-llm` also enables `--style`. It reads `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` from the environment when flags are not provided. The checker only emits sanitized configuration/request errors for LLM-backed style rules and does not print the credential values.

For Python callers, use the module helper instead of shelling out:

```python
from dayamlchecker import RuntimeOptions, find_style_findings_from_string

findings = find_style_findings_from_string(
    interview_yaml,
    input_file="interview.yml",
    runtime_options=RuntimeOptions(style_include_llm=True),
)
```

## URL checks

The main `dayamlchecker` CLI also runs the URL checker by default. Broken URLs in question files fail the command; broken URLs in related `data/templates` files are warnings by default. Use `--no-url-check` to skip it, or tune it with flags such as `--url-check-timeout`, `--url-check-ignore-urls`, `--url-check-skip-templates`, `--template-url-severity`, and `--unreachable-url-severity`.

Current accessibility checks focus on objective failures only:

- Missing alt text in markdown images
- Missing alt text in Docassemble `[FILE ...]` image tags
- Missing alt text in HTML `<img>` tags
- Skipped markdown heading levels such as `##` to `####`
- Skipped HTML heading levels such as `<h2>` to `<h4>`
- Empty link text
- Non-descriptive link text such as `click here`, `here`, `read more`, and Spanish equivalents like `haga clic aquí`
- `no label` and empty/missing labels on multi-field screens (allowed on single-field screens)
- Low contrast in custom Bootstrap theme CSS loaded by `features: bootstrap theme`; inspects actual CSS values for body text, navbar, dropdown menu, and buttons (minimum ratio 4.5:1)

Optional runtime-gated accessibility checks:

- `combobox` usage, including `datatype: combobox` when `--accessibility-error-on-widget combobox` is enabled

Accessibility informational notes are also emitted for likely PDF accessibility issues:

- DOCX attachments missing `tagged pdf: True` (set this in `features` or on the attachment)

WCAG checks still report YAML parse errors, so CI/CD can surface broken YAML and accessibility failures in one run.

This mode is source-based static analysis. It does not audit rendered pages for runtime behavior or JavaScript-created accessibility issues.
