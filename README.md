# DAYamlChecker

An LSP for Docassemble YAML Interviews

## How to run

```bash
pip install .
dayaml check              # defaults to ./docassemble
dayaml format             # defaults to ./docassemble
dayaml check path/to/yaml-or-dir
dayaml check --show-experimental path/to/yaml-or-dir
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

### Real Errors

| Code | Meaning |
| --- | --- |
| `E101` | Duplicate YAML key |
| `E102` | YAML parsing error |
| `E201` | Jinja2 syntax error |
| `E202` | Jinja2 template error |
| `E301` | Unknown YAML keys |
| `E501` | Combobox widget is not accessible |
| `E502` | Field label is missing on a multi-field screen |
| `E503` | DOCX attachment is missing `tagged pdf` |
| `E504` | Bootstrap theme CSS has low contrast |
| `E505` | Image is missing alt text |
| `E506` | Markdown heading levels skip |
| `E507` | HTML heading levels skip |
| `E508` | Link has no accessible text |
| `E509` | Link text is too generic |

### Warnings

| Code | Meaning |
| --- | --- |
| `W101` | Value should be a YAML string |
| `W111` | Invalid Mako syntax |
| `W112` | Mako compile error |
| `W121` | Python code block must be a YAML string |
| `W122` | Python syntax error |
| `W201` | JavaScript modifier must be a string |
| `W202` | Invalid JavaScript syntax |
| `W203` | JavaScript modifier must contain at least one `val()` call |
| `W204` | `val()` references a field not defined on this screen |
| `W205` | `val()` argument must be a quoted string literal |
| `W301` | Malformed `show if` shorthand |
| `W302` | `show if: code` must be a YAML string |
| `W303` | `show if: code` has a Python syntax error |
| `W304` | `show if` dict must include `variable` or `code` |
| `W401` | Python variable reference must be a YAML string |
| `W402` | Python variable reference cannot contain whitespace |
| `W403` | `objects` block must be a list or dict |
| `W404` | `fields: code` must be a YAML string |
| `W405` | Bare `fields` dict has no recognized field or `code` key |
| `W406` | `fields` must be a list or dict |
| `W407` | Field modifier `variable` must be a string |
| `W408` | Field modifier `variable` references a field not defined on this screen |
| `W409` | Field modifier `code` contains another validation error |
| `W410` | `show if: code` references a variable defined on the same screen |
| `W411` | Field modifier dict must include `variable` or `code` |
| `W412` | Field modifier shorthand references a field not defined on this screen |
| `W601` | No recognized block type found |
| `W602` | Block matches too many exclusive interview types |
| `W603` | Interview-order block is missing a matching show/hide guard |
| `W604` | Show/hide visibility logic is nested too deeply |

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
