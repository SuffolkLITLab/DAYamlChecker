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

## Spelling checks

Spelling checks run by default on visible questions, labels, choices, help,
and template content, locally. The default is US English, using the Hunspell
dictionary bundled with [Spylls](https://spylls.readthedocs.io/en/latest/hunspell/dictionary.html)
plus a small reviewed English legal and interface vocabulary. Possible mistakes produce
`WG701` (`spelling_possible_typo`). Spelling is independent of `--style`
and never rewrites text. Use `--no-spellcheck` to disable it.

`--spellcheck-severity info|warning|error` controls the level of all spelling
findings; the default is `warning`. At `error`, spelling findings cause a nonzero
exit code. At `info`, they produce GitHub notices and do not count toward
`--max-warnings`. Rule codes stay stable at every level so suppressions continue
to work.

```bash
python -m dayamlchecker path/to/interview.yml
python -m dayamlchecker --spellcheck-severity error path/to/interview.yml
python -m dayamlchecker --no-spellcheck path/to/interview.yml
python -m dayamlchecker --spellcheck-wordlist project-words.txt path/to/interview.yml
python -m dayamlchecker --spellcheck-ignore-word Urbana path/to/interview.yml
python -m dayamlchecker --spellcheck-language es path/to/interview.yml
python -m dayamlchecker --spellcheck-language en --spellcheck-language es path/to/interview.yml
```

Word lists are UTF-8, one word per line, with `#` comment lines. The repeatable
`--spellcheck-wordlist` option adds project-specific suppressions. Matching is case
insensitive; standard `--suppress` and `# no-dayc: WG701` suppressions apply.
Use repeatable `--spellcheck-ignore-word WORD` for individual suppressions.
Both options affect only the current invocation; they do not alter dictionaries.

`--spellcheck-language` replaces the English default. Repeat it for mixed-language
interviews: a word accepted by **any** selected dictionary is accepted, including
when languages mix within one sentence. Block `language:` and interview
`default language:` declarations determine which blocks are eligible; declarations
whose base language is not selected are skipped. Unlabelled text uses all selected
dictionaries. This is explicit dictionary selection, not automatic language detection.
Selecting more languages can also hide a typo that is a valid word in another language.

Built-in languages are `en` (US English), `es` (US Spanish), `ru` and `sv` (Swedish).
`en-US`/`en_US`, `es-US`, `ru-RU` and `sv-SE` are equivalent aliases. Block tags such
as `es-MX` match selected `es`; regional dictionary selection such as `en-GB`
requires a custom dictionary. English, Russian and Swedish dictionaries come
with Spylls and never require network access.

Spanish uses the RLA-ES Hunspell dictionary distributed by LibreOffice,
including inflection rules and accented words. It is not shipped with this
package: the first run that selects `es` downloads it (about 850 KB) from a
pinned LibreOffice commit, verifies its SHA-256 hashes, and caches it in
`$XDG_CACHE_HOME/dayamlchecker` (default `~/.cache/dayamlchecker`;
`%LOCALAPPDATA%\dayamlchecker\cache` on Windows). Later runs on the same machine
reuse the cache. Set `DAYAMLCHECKER_CACHE_DIR` to choose another location, for
example one saved with `actions/cache`. Fresh CI runners download it once per
run. To work offline, supply a local copy with `--spellcheck-dictionary es=PATH`.

For other languages or dialects, provide a Hunspell `.aff`/`.dic` pair:

```bash
# Loads /path/to/fr_FR.aff and /path/to/fr_FR.dic; selects French.
python -m dayamlchecker --spellcheck-dictionary fr=/path/to/fr_FR interview.yml
# Mixes English with the supplied French dictionary.
python -m dayamlchecker --spellcheck-language en --spellcheck-language fr \
  --spellcheck-dictionary fr=/path/to/fr_FR interview.yml
```

Dictionary flags are repeatable and can override built-in dictionaries. With no
language flags, the supplied dictionary language codes become the selected languages.
Unknown language codes and missing dictionary files produce configuration errors.
`--no-spellcheck` disables the pass even when language or suppression options
are supplied. The optional `--spellcheck` flag explicitly enables it.

Python callers can use `dayamlchecker.find_spelling_findings_from_string(yaml_text)`
or pass options to the existing checker functions:

```python
from dayamlchecker import (
    RuntimeOptions,
    SpellcheckOptions,
    find_spelling_findings_from_string,
)
from dayamlchecker.messages import Severity

options = RuntimeOptions(
    spellcheck=SpellcheckOptions(
        severity=Severity.WARNING,  # Or Severity.INFO / Severity.ERROR.
        allowed_words=frozenset({"Urbana", "ProjectName"}),
        languages=("en", "es"),
        # Optional: dictionaries=(("fr", "/path/to/fr_FR"),),
    )
)
findings = find_spelling_findings_from_string(yaml_text, runtime_options=options)
```

For the main Python checker APIs, set `RuntimeOptions(spellcheck=None)`
to disable the pass. The spelling-only convenience API always runs it.

Common legal spellings have explicit recommendations under `WG702`
(`spelling_common_legal_typo`): `judgement` → `judgment` and `judgements` →
`judgments` in US English, and `HIPPA` → `HIPAA` when English is selected.
These checks also cover capitalization, possessives and hyphenated compounds
such as `judgement-proof` and `HIPPA-compliant`. They bypass dictionary-accepted
variants and acronym filtering. Custom British English dictionaries keep their
own accepted variants for `judgement`. Word lists, `--spellcheck-ignore-word`,
`--suppress WG702` and `# no-dayc: WG702` can suppress these recommendations.

The pass excludes code, stored choice values, object-choice expressions, Mako
expressions, HTML attributes, links' destinations, icons, and Markdown code.
It accepts possessives, recognized hyphenated compounds and spelling variants.
Blocks outside selected languages and long passages mostly outside the selected
dictionaries are skipped. Metadata is excluded. Capitalized names declared in
`metadata.authors` are recognized if they appear in visible prose. Personal-name
spans in contributor, author, credit and copyright sections are excluded, while
ordinary prose in those sections remains checked.

Capitalized court, county, parish, city and other geographic choice labels are
recognized from the field's label, variable or help; this works across
jurisdictions without a county-name dictionary. Questions and instructions on
those screens remain checked. Other unfamiliar capitalized words produce a
warning only when a nearby lowercase dictionary word supplies spelling evidence
(a single insertion, deletion or transposition). This rule applies at the start
of sentences as well as within them. Acronyms, mixed-case identifiers and short
tokens also receive conservative treatment. Accented tokens are skipped in the
default English-only mode and checked with multilingual/custom dictionaries.
Consequently it can miss typos, particularly in names, capitalized words and valid
words used incorrectly. Locations point to the containing YAML key or field.

The October 2026 experiment on `~/all_interviews` is recorded in
[`reports/spelling_corpus_review.json`](reports/spelling_corpus_review.json).
Reproduce the comparison without running unrelated lints or URL requests:

```bash
python scripts/evaluate_spelling.py ~/all_interviews --output /tmp/spelling.json
# Optional: --language en --language es --wordlist project-words.txt
# Custom dictionaries: --dictionary fr=/path/to/fr_FR
```

The evaluation reports raw dictionary warnings versus filtered warnings, with
file, word and context for manual review. A warning count alone is not a
false-positive count. The earlier pass had no corpus-specific name list: of 45
warnings, contextual review identified 44 typos and one organization-name false
positive. It misses the two misspelled car brands found in the earlier run.
The rules were developed on this corpus, so these figures are not an independent
accuracy measurement. Upstream issue links are saved in
[`reports/spelling_issues.json`](reports/spelling_issues.json).

Before adding the legal spelling recommendations, the English–Spanish run on
the same 180 files produced 44 warnings: the same 44
reviewed typos, with `Urbana` accepted by the Spanish dictionary and no new warnings.
The English-only warning set was unchanged. That run gave zero reviewed false positives
on this corpus with both languages enabled; it does not establish the accuracy of
Spanish checking on other interviews. Results and commands are recorded in
[`reports/spelling_language_evaluation.json`](reports/spelling_language_evaluation.json).

With the default-on pass and legal recommendations, the same corpus produces 50
English-only findings and 49 English–Spanish findings. Five new recommendations
replace `judgement`/`judgements` in references to court judgments. The earlier
warning sets remain intact; the reviewed false-positive counts remain one for
English and zero for English–Spanish. No visible `HIPPA` occurrences were found
in the corpus. The additions and reproducible commands are in
[`reports/spelling_default_evaluation.json`](reports/spelling_default_evaluation.json).

## Jinja2 preprocessing

Files whose first line is exactly `# use jinja` (LF, CRLF, or end of file) are
rendered before the normal validation
pass, following docassemble's [YAML preprocessing feature](https://docassemble.org/docs/interviews.html#jinja2).
Expressions, loops, conditionals, macros, and local includes are supported.
Include paths are relative to the input file's directory; includes can contain
partial YAML blocks. Ordinary YAML files and Mako expressions are unaffected.

This is an offline check: server configuration, `jinja data`, docassemble's
special context variables, and package-qualified includes are not supplied.
Unknown variables are treated as empty values throughout -- in arithmetic and
comparisons, and through every built-in filter and test -- so interviews that
use server-side Jinja context can still be checked; a branch that tests one is
taken as if the value were empty, and only that branch is checked. An expression
that renders to such a value is replaced with a placeholder and reported as
`WG107`, described below. Missing imports and parent templates produce `EG106`.
Rendering uses Jinja's sandbox and disables HTML escaping. Compilation
and rendering run in an isolated worker with a 5-second wall timeout and 2-second
CPU limit. Linux and other supported Unix platforms also use a 256 MiB
address-space limit; macOS skips that limit because Darwin rejects limits below
the process's existing virtual address space. Source and rendered output are
limited to 4 MiB each.
Exceeding a limit produces `EG106`. Bounded rendering requires Unix resource-limit
support; other platforms report `EG106` rather than rendering without limits.
Ordinary YAML checking does not require these limits.

Jinja syntax and runtime errors identify the original template file and line,
including nested local templates, so their source-level suppressions work.

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

Expressions that depend on values only the server supplies produce warning
`WG107`. Rather than rendering to nothing -- which would leave an empty YAML
value, an invalid Python line, or a block with no `id`, and hide every real
problem around it -- each one is replaced with a placeholder such as
`dayc_unknown_1`, so the surrounding document stays parseable and is still
checked. Each placeholder is distinct, so two unknown block ids do not look
like duplicates of each other. The warning names the variable and points at the
line of the original template, and one source site produces one warning however
many times it renders.

Nothing that depends on the real value is checked, so a later block that relies
on what an earlier expression produced may be checked against the placeholder
instead. Checks that resolve a name against the rest of the interview stay quiet
when a placeholder is involved; anything else can be suppressed with
`# no-dayc: WG107` on the line or `# no-dayc-block: WG107` in its source block,
which -- like `WG106` -- refer to the original template, not the rendered YAML.

Missing includes and unknown values are skipped by default and do not fail CI
unless a warning limit such as `--max-warnings 0` is set. You can suppress the partial-validation
warning with `# no-dayc: WG106` on the include or `# no-dayc-block: WG106` in its
source block.

Other errors, including missing imports and parent templates (`EG106`), still
fail by default. Explicitly suppress a known dependency-related
rendering limitation with a source-level suppression, for example:

```yaml
# use jinja
# no-dayc-block: EG106
{% import "external-macros.yml" as framework %}
```

Rendering errors also honor source suppressions, but a rendering failure prevents
validation of the remaining file. Missing includes alone allow partial validation;
suppressing their warning does not suppress errors in the remaining YAML.

Findings after preprocessing name the original file but are labeled
`(rendered Jinja)`; their line numbers and suppression comments refer to the
rendered YAML, not the original template. `--format github` therefore annotates
the file as a whole and reports the generated line in the message, so the
annotation resolves without pointing at an unrelated source line. Only the
rendered branches are checked. `--fix` skips these files because generated line
numbers cannot safely identify source edits.
Template-aware formatting is outside this feature's scope.

## Suppressing checks

You can suppress specific errors or warnings by their ID or finding class (`accessibility`, `style`, `translatability`, `spelling`, `general`). 

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

`WT705` flags negative contractions (`can't`, `don't`, `won't`) and complex
contractions (`could've`, `should've`, `would've`, `they've`) for translation
clarity and non-native reader comprehension, following
[GOV.UK guidance](https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/clear-language/).
Simple positive forms such as `you'll`, `it's`, `what's`, `we're`, and `I'm`
are allowed. Straight and curly apostrophes are checked. The historical
`style_contraction` message ID and `WS727` suppression code still work;
the finding now belongs to `translatability`, so suppressing `style` alone
does not hide it.

Length checks measure visible conditional alternatives, and prose checks keep
paragraphs and list items separate. Field counts exclude presentation items and
count related parts of the same address as one input. Separate addresses count
separately. Simple boolean visibility is checked for simultaneously visible
inputs, including literal comparisons and indexed references. Generated fields
and unsupported visibility expressions produce count-coverage advisories when
they could conceal an overloaded screen.
The complex-screen help check also groups ordinary name components.

A custom theme is optional. Use `--style-require-custom-theme` (which also
enables `--style`) or `RuntimeOptions(style_require_custom_theme=True)` to
require one. Theme and eligibility checks read locally available includes
without executing interview code. When an include cannot be resolved, those
checks report coverage as uncertain unless available evidence already establishes
the theme or exit. Top-level `help`, including `{label, content}`, opens a separate
Help interface and is discouraged; use inline contextual help instead. Review
action destinations, table edit definitions, and cell-level edit links are
checked using available local includes. Document previews normally have a Back
route; they are flagged only when that route is explicitly disabled and no
correction control is detected. Unresolved review widgets alone do not produce
findings. Wall-of-text checks measure individual paragraphs, list items, and
table cells, including soft wraps. Short chunks are not added together to create
a length warning; an individual chunk over 120 words still warns even when
the rest of the screen is well formatted.

Vocabulary checks favor recall. `IS712` suggests simpler wording for `please`,
`select`, and `option`. `IS746` asks authors to review `request`, `report`,
`benefit`, and `following` in context, with alternatives that distinguish verbs
from nouns and preserve official names. These are informational suggestions,
not automatic source edits. The seven candidates have a separate match budget
so they do not displace other plain-language findings. `Review` remains allowed,
and the unsafe blanket mappings for `the tenant`, `find`, `it is`, `application`,
`added`, and `condition` remain disabled.

```bash
python3 -m dayamlchecker --style --no-url-check path/to/interview.yml
python3 -m dayamlchecker --style-llm --openai-api-key "$OPENAI_API_KEY" path/to/interview.yml
OPENAI_BASE_URL=https://api.openai.com/v1 OPENAI_API_KEY=... python3 -m dayamlchecker --style-llm path/to/interview.yml
```

`--style-llm` also enables `--style`. It reads `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` from the environment when flags are not provided. The checker only emits sanitized configuration/request errors for LLM-backed style rules and does not print the credential values.

With `--style-llm`, a contextual triage pass reviews those seven vocabulary
candidates in batches of at most 20, across all screens. This adds one request
per batch to the existing broad style reviews. A candidate is dismissed only
when the model supplies a high-confidence dismissal with a literal contextual
quote. Uncertainty, truncated context, missing credentials, request failures,
or invalid/incomplete responses retain the deterministic findings. Other
deterministic checks cannot be dismissed by this pass. Retained candidates
include the model's reason and quote in their finding context; a confirmed
candidate can receive a more grammatical suggestion. Response validation
guards the triage protocol; it does not guarantee the model's judgment is
correct. Corpus audits run without model calls by default.

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
