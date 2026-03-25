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
python3 -m dayamlchecker --wcag path/to/interview.yml
```

This is equivalent to `wcag=true` in the frontend. Use `--no-wcag` for `wcag=false`.

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
- `combobox` usage, including `datatype: combobox`
- `no label` and empty/missing labels on multi-field screens (allowed on single-field screens)
- Low contrast in custom Bootstrap theme CSS loaded by `features: bootstrap theme`; inspects actual CSS values for body text, navbar, dropdown menu, and buttons (minimum ratio 4.5:1)

Accessibility informational notes are also emitted for likely PDF accessibility issues:

- DOCX attachments missing `tagged pdf: True` (set this in `features` or on the attachment)

WCAG checks still report YAML parse errors, so CI/CD can surface broken YAML and accessibility failures in one run.

This mode is source-based static analysis. It does not audit rendered pages for runtime behavior or JavaScript-created accessibility issues.
