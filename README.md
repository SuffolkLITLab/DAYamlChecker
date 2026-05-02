# DAYamlChecker

An LSP for Docassemble YAML Interviews

## How to run

```bash
pip install .
dayaml check              # defaults to ./docassemble
dayaml format             # defaults to ./docassemble
dayaml check path/to/yaml-or-dir
dayaml check --show-experimental path/to/yaml-or-dir
dayaml check --ignore-codes E410,E301 path/to/yaml-or-dir
dayaml check --format-on-success --no-url-check path/to/yaml-or-dir
dayaml format path/to/interview.yml

# Backwards-compatible entry points
python3 -m dayamlchecker `find . -name "*.yml" -path "*/questions/*" -not -path "*/.venv/*" -not -path "*/build/*"` # i.e. a space separated list of files
dayamlchecker `find . -name "*.yml" -path "*/questions/*" -not -path "*/.venv/*" -not -path "*/build/*"`
dayamlchecker-fmt path/to/interview.yml
```

## Message Codes

Validation output now includes stable message codes in the style of tools like pylint:

```text
[E301] At interview.yml:12: Keys that shouldn't exist! ['not_a_real_key']
```

Use `dayaml check --show-experimental ...` to include the legacy `REAL ERROR:`
prefix for non-experimental errors.

Use `dayaml check --ignore-codes E410,E301 ...` to suppress specific
diagnostic codes when you need to waive known findings.

`dayaml` also reads optional project settings from `pyproject.toml`:

```toml
[tool.dayaml]
ignore_codes = ["E503", "E410"]
yaml_path = "docassemble"
args = ["--no-url-check"]
```

When you pass a project root that contains `pyproject.toml`, `dayaml` scans the
configured `yaml_path` relative to that file. If `yaml_path` is omitted, it
defaults to `docassemble`.

`tool.dayaml.args` lets you set checker CLI defaults in the project config.
Those args are applied before the actual command-line args, so an explicit CLI
flag still wins. For example, `args = ["--no-url-check"]` disables URL checks
by default, while `dayaml check --url-check ...` turns them back on for one run.

`dayaml check --format-on-success ...` validates each file first and then runs
the formatter on files that have no error-severity findings after ignore-code
filtering. This uses the already-read file content in memory, so it avoids a
separate checker-then-formatter pass over the same file. Formatting happens
before the later URL-check phase, so a run can still exit nonzero for URL
errors after formatting changes have already been written. Use
`--no-url-check` with this mode if you want the combined YAML-check-and-format
behavior without the later repository URL scan.

### Real Errors

| Code | Meaning |
| --- | --- |
| `E101` | Duplicate YAML key |
| `E102` | YAML parsing error |
| `E103` | Value should be a YAML string |
| `E111` | Invalid Mako syntax |
| `E112` | Mako compile error |
| `E121` | Python code block must be a YAML string |
| `E122` | Python syntax error |
| `E201` | Jinja2 syntax error |
| `E202` | Jinja2 template error |
| `E203` | JavaScript modifier must be a string |
| `E204` | Invalid JavaScript syntax |
| `E205` | JavaScript modifier must contain at least one `val()` call |
| `E206` | `val()` references a field not defined on this screen |
| `E207` | `val()` argument must be a quoted string literal |
| `E301` | Unknown YAML keys |
| `E302` | Malformed `show if` shorthand |
| `E303` | `show if: code` must be a YAML string |
| `E304` | `show if: code` has a Python syntax error |
| `E305` | `show if` dict must include `variable` or `code` |
| `E306` | No recognized block type found |
| `E307` | Block matches too many exclusive interview types |
| `E308` | Interview-order block is missing a matching show/hide guard |
| `E309` | Show/hide visibility logic is nested too deeply |
| `E401` | Python variable reference must be a YAML string |
| `E402` | Python variable reference cannot contain whitespace |
| `E403` | `objects` block must be a list or dict |
| `E404` | `fields: code` must be a YAML string |
| `E405` | Bare `fields` dict has no recognized field or `code` key |
| `E406` | `fields` must be a list or dict |
| `E407` | Field modifier `variable` must be a string |
| `E408` | Field modifier `variable` references a field not defined on this screen |
| `E409` | Field modifier `code` contains another validation error |
| `E410` | `show if: code` references a variable defined on the same screen |
| `E411` | Field modifier dict must include `variable` or `code` |
| `E412` | Field modifier shorthand references a field not defined on this screen |
| `E501` | Combobox widget is not accessible |
| `E502` | Field label is missing on a multi-field screen |
| `E503` | DOCX attachment is missing `tagged pdf` |
| `E504` | Bootstrap theme CSS has low contrast |
| `E505` | Image is missing alt text |
| `E506` | Markdown heading levels skip |
| `E507` | HTML heading levels skip |
| `E508` | Link has no accessible text |
| `E509` | Link text is too generic |

### Conventions

| Code | Meaning |
| --- | --- |
| `C101` | `validation code` should call `validation_error()` |

## WCAG checks

The checker includes WCAG-style checks for clear static accessibility failures in interview source. These checks run by default; use `--no-wcag` to disable them.

```bash
python3 -m dayamlchecker path/to/interview.yml          # WCAG checks on (default)
python3 -m dayamlchecker --no-wcag path/to/interview.yml  # WCAG checks off
python3 -m dayamlchecker --accessibility-error-on-widget combobox path/to/interview.yml  # opt into combobox accessibility errors
```

Some accessibility checks are behind runtime options while the rules are still being evaluated. Right now `combobox` failures are default-off and can be enabled with `--accessibility-error-on-widget combobox`.

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

Accessibility errors are also emitted for likely PDF accessibility issues:

- DOCX attachments missing `tagged pdf: True` (set this in `features` or on the attachment)

WCAG checks still report YAML parse errors, so CI/CD can surface broken YAML and accessibility failures in one run.

This mode is source-based static analysis. It does not audit rendered pages for runtime behavior or JavaScript-created accessibility issues.
