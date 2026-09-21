# DAYamlChecker

An LSP for Docassemble YAML Interviews

## How to run

```bash
pip install .
python3 -m dayamlchecker `find . -name "*.yml" -path "*/questions/*" snot -path "*/.venv/*" -not -path "*/build/*"` # i.e. a space separated list of files
```

For the conservative, deterministic fixes supported by the checker, add
`--fix`. It writes only changes that validate after editing, then runs the
normal checker against the updated files. The fixes add missing question IDs,
expand yes/no shortcuts, label the first offending field on a multi-field
screen, and suffix later duplicate block IDs. A dry run is still available via
the standalone `scripts/fix_yaml_checker.py` tool.

`--fix` respects `--no-wcag` and `--suppress`: it never rewrites source for a
rule the run would not report. A candidate edit is written only when it parses,
introduces no new finding of any rule, and actually removes the finding it was
made for; anything else is reported on stderr and left alone. A file the fixer
cannot safely rewrite is not itself an error, so it does not fail the run.

```bash
python3 -m dayamlchecker --fix path/to/interview.yml
```

## Jinja2 preprocessing

Files beginning with `# use jinja` are rendered before the normal validation
pass, following docassemble's [YAML preprocessing feature](https://docassemble.org/docs/interviews.html#jinja2).
Expressions, loops, conditionals, macros, and local includes are supported.
Include paths are relative to the input file's directory; includes can contain
partial YAML blocks. Ordinary YAML files and Mako expressions are unaffected.

This is an offline check: server configuration, `jinja data`, docassemble's
special context variables, and package-qualified includes are not supplied.
Missing variables, imports, and parent templates produce `EG105`. Rendering
uses Jinja's sandbox and disables HTML escaping.

Missing `{% include %}` files (including unavailable package-qualified paths)
produce warning `WG106`: the included Jinja2 document could not be verified and
findings are partial. The checker substitutes a marker, skips each rendered YAML
document containing that marker, and checks the remaining documents. This also
applies to `ignore missing`; include fallback lists try all candidates first.
Repeated execution of the same include site produces one diagnostic.

Partial validation is best effort. An unavailable include may itself supply YAML
document boundaries or Jinja definitions, so the remaining output may differ from
the real interview. A partial-block include causes its entire containing YAML
document to be skipped. Findings retain rendered line numbers.

Missing includes are skipped by default and do not fail CI unless a warning
limit such as `--max-warnings 0` is set. You can suppress the partial-validation
warning with `# no-dayc: WG106` on the include or `# no-dayc-block: WG106` in its
source block.

Other errors, including missing Jinja variables, imports, and parent templates
(`EG105`), still fail by default. Explicitly suppress a known dependency-related
rendering limitation with a source-level suppression, for example:

```yaml
# use jinja
# no-dayc-block: EG105
{% import "external-macros.yml" as framework %}
```

Rendering errors also honor source suppressions, but a rendering failure prevents
validation of the remaining file. Missing includes alone allow partial validation;
suppressing their warning does not suppress errors in the remaining YAML.

Findings after preprocessing use a virtual filename ending in `(rendered Jinja)`;
their line numbers and suppression comments refer to the rendered YAML, not the
original template. Only the rendered branches are checked. `--fix` skips these
files because generated line numbers cannot safely identify source edits.
Template-aware formatting is outside this feature's scope.

## Suppressing checks

You can suppress specific errors or warnings by their ID or finding class (`accessibility`, `style`, `translatability`, `general`). 

**Inline and block comments in YAML:**
To suppress a finding on a specific line, use a `# no-dayc: ` comment:
```yaml
question: Second  # no-dayc: EG101
```
To suppress findings for an entire document or block, use `# no-dayc-block: ` inside the block (e.g., after the `---` document marker):
```yaml
---
# no-dayc-block: style, WG123
code: |
  answer = 1
```
You can use `ALL` or `*` to suppress all findings on a line/block (`# no-dayc: ALL`). Multiple codes can be separated by spaces or commas.

**Command-line argument:**
To globally suppress findings across all files being checked, pass a comma-separated list of IDs or classes to the `--suppress` parameter:
```bash
python3 -m dayamlchecker --suppress accessibility,EG101 path/to/interview.yml
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

Assembly Line style checks are opt-in. Enable them with `--style` to run
deterministic style and translatability findings ported from ALLinter without
duplicating the checker’s existing YAML, accessibility, or URL coverage.

Translatability findings have their own `translatability` finding class and
use `WT` warning codes. They include translated choice labels that lack
invariant stored values, user-facing strings embedded in code, and conditional
expressions or Mako blocks that change only part of a sentence.

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
- Templates used with `display_template()` that have a missing or empty `subject`

Optional runtime-gated accessibility checks:

- `combobox` usage, including `datatype: combobox` when `--accessibility-error-on-widget combobox` is enabled

Accessibility informational notes are also emitted for likely PDF accessibility issues:

- DOCX attachments missing `tagged pdf: True` (set this in `features` or on the attachment)

WCAG checks still report YAML parse errors, so CI/CD can surface broken YAML and accessibility failures in one run.

This mode is source-based static analysis. It does not audit rendered pages for runtime behavior or JavaScript-created accessibility issues.

## DOCX template checks

Any `.docx` files you pass on the command line are checked for static
accessibility problems in the documents users receive: missing alt text,
empty or ambiguous link text, missing language metadata, heading structure,
table header and merged-cell risks, explicitly low-contrast text, and
floating objects or text boxes that disturb reading order. These run by
default; use `--no-docx-accessibility` to skip them.

DOCX files are also checked for embedded comments and tracked-change markup.
These are errors by default because drafting material can leak into published
documents or change their output. Accept or reject all changes and remove all
comments before committing a template. Use `--no-docx-review-markup` to disable
only this rule while keeping the accessibility checks, or suppress `EG130` with
the standard `--suppress` option. The existing `--no-docx-accessibility` master
switch disables all DOCX checks, including this one.

**Every finding is capped at warning severity by default**, so turning these
checks on reports problems without failing the build. Most existing
templates have findings today, and the intent is for authors to work through
them over time rather than to block a release. Opt into failing with
`--docx-accessibility-severity error`, which restores each rule's own
severity.

```bash
# Report findings without failing (the default)
python3 -m dayamlchecker docassemble/MyPackage/data/templates

# Fail the command when a document has accessibility errors
python3 -m dayamlchecker --docx-accessibility-severity error docassemble/MyPackage/data/templates
```

DOCX findings use the same diagnostic codes, `--suppress`, `--format github`
and `--max-warnings` machinery as every other check. They are numbered
`EA540`-`IA567` in the accessibility range, so a single noisy rule is
silenced the usual way:

```bash
python3 -m dayamlchecker --suppress IA561 ...   # missing document title
```

Because a DOCX has no line numbers, findings name the package part they came
from (`word/document.xml`, `word/header1.xml`) and quote up to 80 characters
of nearby text so you can search the document for the problem:

```
WARN  [WA552] docassemble/MyPackage/data/templates/discovery.docx
  a table in word/document.xml has no obvious header row marker
  (table begins "Certificate of Service")
IA565  the document contains 48 empty paragraphs used for spacing, the
  longest run being 7 (longest run is near "v.")
```

Tables quote their first text, images and text boxes quote the paragraph
beside them, and empty-paragraph runs quote what precedes them. Findings that
would otherwise read identically are kept separate, so two tables with the
same problem are two findings rather than one.
