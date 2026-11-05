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
`SP701` (`spelling_possible_typo`). Spelling is independent of `--style`
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
insensitive; standard `--suppress` and `# no-dayc: SP701` suppressions apply.
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

Common legal spellings have explicit recommendations under `SP702`
(`spelling_common_legal_typo`): `judgement` → `judgment` and `judgements` →
`judgments` in US English, and `HIPPA` → `HIPAA` when English is selected.
These checks also cover capitalization, possessives and hyphenated compounds
such as `judgement-proof` and `HIPPA-compliant`. They bypass dictionary-accepted
variants and acronym filtering. Custom British English dictionaries keep their
own accepted variants for `judgement`. Word lists, `--spellcheck-ignore-word`,
`--suppress SP702` and `# no-dayc: SP702` can suppress these recommendations.

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

With `--style-llm`, contextual triage reviews **every** plain-language replacement
candidate in batches of at most 20. Precision mode shows only changes the model
confirms with high confidence and a literal quote. It hides unconfirmed word
suggestions, including when AI is off or a request fails; failures are reported
separately. Thorough mode keeps unconfirmed suggestions for manual review.
The filter preserves document names, quotes, and wording whose meaning would
change. It cannot dismiss other kinds of checks.

`--readiness-research` also runs this vocabulary filter with the research model
(default `gpt-6.1-terra`). These extra requests are separate from the web research
budget. On the main CLI, `--readiness --style-llm` enables the full AI style review
without requiring web research; `--openai-model` selects its model.
Research findings should lead with an action, use short plain sentences, merge
related issues, and distinguish added risks from limits inherited from the court
form. Model judgments still need review.

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

### Precision-focused style review and stronger models

`--style` now defaults to `--style-review-level precision`. It omits unknown
field-count advisories and unconfirmed, context-sensitive vocabulary suggestions.
For example, generated `users[0].name_fields()` is not itself evidence of an
unclear screen. Use `--style-review-level thorough` to include those candidates
for editorial review. Neither mode turns off concrete structural errors.

Choice labels such as Yes, No, and Other are evaluated with their question or
field label. A dedicated Continue button is normal navigation. Blank and
symbol-only labels are still checked. Plain field labels such as Other may
still need a more descriptive accessible name.

LLM review remains optional. It now receives field labels, variables, choices,
and generated-field expressions, reviews screens in batches rather than silently
stopping after the first 40 blocks, and accepts only quotes grounded in an
identified screen. The checker reports at most one finding per screen per LLM
rule. Interview text is treated as data, not instructions.

```bash
dayamlchecker ./docassemble --style-llm --openai-model gpt-6.1-terra
dayamlchecker ./docassemble --style --style-review-level thorough
```

`OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` configure an
OpenAI-compatible endpoint; `--openai-model` overrides the environment model.
Use the deployment ID supported by your provider. The inexpensive default
remains `gpt-4o-mini`; model selection and review breadth are independent.
Live evaluations used available provider deployments; availability varies by
endpoint. See the [validation summary](docs/readiness-validation.md) for the
sample sizes and limitations. Model output can still contain false positives.

To repeat the deterministic corpus evaluation:

```bash
python scripts/evaluate_style.py ~/all_interviews/repos --stride 3 --output /tmp/style-results.json
```

This checks every third sorted repository, all top-level question YAML files,
and all static style/accessibility rules. Counts are candidate counts, not a
measurement of precision. `--llm --model MODEL` also enables paid model calls.

### Publication pre-flight

```bash
dayamlchecker --readiness /path/to/docassemble-package > /tmp/readiness.json
# Defaults to the current directory:
dayamlchecker --readiness
# The separate command remains available:
dayamlchecker-readiness /path/to/docassemble-package
# Equivalent without reinstalling the console scripts:
python -m dayamlchecker.readiness /path/to/docassemble-package
```

The JSON report returns `pass` (exit 0), `blocked` (exit 1), or `needs_review`
(exit 2). Individual checks can also be `warning`, `not_checked`, or
`not_applicable`; warnings do not prevent an overall pass. Schema version 2
records each check's severity and whether it is a release gate. Findings expose
publication-policy `severity`, the original `checker_severity`, and `release_gate`.
The ordinary linter's rules and severities are unchanged.

| Area | Release policy |
| --- | --- |
| Templates and filenames | Static PDF field and DOCX Jinja inspection, naming, locally unmatched variables, overflow concerns, DOCX accessibility and tracked-change checks are advisory. No populated document or interview run is required. |
| Project setup | Weaver initialization is not required. Object conventions and uncertain imported definitions are maintainability advice. |
| Question design and flow | Structural errors and missing prompts without supplemental screen context can block. Sentence length, vocabulary preferences, and uncertain static inferences remain advisory. Human question/flow review is still required. |
| Answer review | Missing usable review is a strong warning for short interviews. At **10 or more statically declared input screens**, it blocks if include coverage is complete, or requires review if unresolved includes might provide editing. Use `--long-interview-screens N` to change the threshold. This is an estimate, not an executed path length. |
| Document delivery | A missing literal local PDF/DOCX template blocks. Literal bundle members are inventoried; empty lists, locally unresolved members, and computed membership are advisory. Dynamic conditions and the actual download set are not proven statically. |
| Live testing | Not a check or release gate in this tool. No running interview/server/browser is required for local checks. |
| GitHub publication | Opt in with `--readiness-github`; otherwise explicitly not checked. Naming concerns are advisory. |

These checks reference the
[authoring checklist](https://assemblyline.suffolklitlab.org/docs/authoring/weaver/authoring_checklist/)
and [maturity model](https://projects.suffolklitlab.org/legal-tech-class/docs/legal-tech-overview/maturity-model/).
The level references organize evidence; they do not certify a maturity level or
constitute official Court Forms Online acceptance.

Use `dayamlchecker --readiness --evidence /path/to/publication-evidence.json`
to supply a JSON object with `source_sha256` copied from the current report and
one object for each of `legal_review`, `plain_language_review`,
`interview_flow_review`, and `publication_review`. Each object requires
`passed: true` and nonempty `reviewer`, `date`, and `evidence` strings. Store the
file outside the repository or name it `publication-evidence.json`. Changed
package contents invalidate previous evidence. The digest covers the `docassemble/`
directory and top-level `LICENSE`, `MANIFEST.in`, `README.md`, `pyproject.toml`,
`setup.cfg`, and `setup.py`. Hidden files/directories, Python bytecode, and that
evidence filename are excluded, so reports and local build output do not
invalidate reviews.
Earlier `scenario_testing`, `template_review`, and `accessibility_review`
attestations are no longer required gates; they are not substitutes for the new
static interview-flow review.

The scan includes nested local question YAML and local PDF/DOCX templates.
It does not execute templates or interviews. A detected review/edit control does
not prove every answer can be edited safely; the flow review covers that remaining
uncertainty. The tool records attestations but cannot verify their truth.

### GitHub publication and unpublished Playground sources

```bash
dayamlchecker --readiness /path/to/repo --readiness-github
# Override the origin-derived repository or current branch:
dayamlchecker --readiness /path/to/repo --readiness-github \
  --github-repository SuffolkLITLab/docassemble-Example --github-ref main
```

GitHub checking is read-only. It compares local HEAD and working-tree changes
with the selected remote ref, reports archived/disabled repositories, and gives
advice about obviously generic/draft repository names. A behind checkout also
needs review: this check asks whether the analyzed snapshot matches the selected
published ref, not whether its commit ever existed online. Set `GITHUB_TOKEN`
or `GH_TOKEN` for private repositories or authenticated rate limits. Network or
permission failures cannot establish publication. CI, issue triage, releases,
and commit-message quality are not currently assessed.

To inspect work that has not been committed, set `DOCASSEMBLE_API_KEY` and use:

```bash
dayamlchecker --readiness \
  --playground-server https://dev.example.org \
  --playground-user author@example.org
# Select projects instead of scanning all of the user's projects:
dayamlchecker --readiness \
  --playground-server http://localhost \
  --playground-user 7 --playground-project Housing --playground-project Benefits
```

`--playground-user` accepts an email (docassemble's API username) or numeric user
ID. Omit it to use the API key owner's Playground. The key must have permission
to read the selected user's projects. The client uses only GET endpoints for
user lookup, project listing, file listing, and file download from the
[docassemble API](https://docassemble.org/docs/api.html). It never creates a
session, runs an interview, uploads files, pulls packages, or modifies the server.
HTTPS is required except for localhost. Redirects are not followed with the key.

Each project is downloaded to a temporary package-shaped snapshot and checked
independently, with original project/file identities and content hashes retained
in the JSON report. Empty/non-interview projects are marked not applicable.
Unreadable projects remain needs-review results, not clean scans. Temporary
copies are deleted afterward. Local modules are read as files, never imported;
installed-library behavior and Playground-specific package references may remain
unresolved. No `.env` file or API key is written into the snapshot/report.

Playground scans are an alternative to a local root. They cannot use
`--readiness-github`, because an unpublished snapshot has no trustworthy Git
commit identity, or one shared `--evidence` file for multiple projects. Research
can be enabled explicitly with `--readiness-research` and then applies to each
selected project, with per-project API costs. A live server is used only to read
source files, not as a requirement to execute the interview.

### Findings for assistant draft repairs

Findings associated with a parsed YAML block carry `context["repair_context"]`:
version, filename, screen ID, block index/start line, source YAML and its SHA-256,
rule location/evidence where available, and a generated-field runtime-verification
flag. The existing stable rule code, message, severity, and line remain available.
The publication report serializes these fields as JSON. Syntax errors without a
parsed block retain their normal diagnostics rather than invented source context.

Repair clients should verify the source hash, preserve template/runtime code,
and validate any proposed patch. For Jinja-rendered findings, honor
`rendered_jinja`; the block source and line refer to rendered YAML, not necessarily
the original template. No repair is generated or applied by this interface.
ALWeaver's current `dayamlchecker_findings()` adapter copies message, severity,
and line but does not yet forward `context`; that adapter needs to pass through
`repair_context` when connecting these findings to assistant draft repairs.

### Optional AI research of instructions and next steps

```bash
# Checks local instructions against cited guidance and supplemental web research:
dayamlchecker --readiness /path/to/package --readiness-research

# Additionally inventory claims that need corroboration:
dayamlchecker --readiness /path/to/package --readiness-research \
  --research-strict-unverified

# Optional starting sources and research budget/model overrides:
dayamlchecker --readiness /path/to/package --readiness-research \
  --research-source https://www.example.gov/court/filing-guide \
  --research-model gpt-6.1-terra --research-timeout 180 \
  --research-max-tool-calls 12
```

The default research model is `gpt-6.1-terra`, independent of the style model.
The same research flags work with `dayamlchecker-readiness`. Research is off by
default and uses paid Responses API calls with the `web_search` tool. Configure
`OPENAI_API_KEY` and `OPENAI_BASE_URL`, or the corresponding `--openai-api-key`
and `--openai-base-url` options. Azure requires a deployment on the selected
account and an endpoint supporting Responses web search. No model is silently
substituted if the deployment or tool is unavailable.

Research starts with metadata such as `help_page_url`, other cited URLs, and any
`--research-source` URLs. It can open pages, follow relevant child articles on
multi-page sites, and search the web when references are missing, insufficient,
inaccessible, or conflicting. The agent compares filing/service instructions,
eligibility, deadlines, fees, hearings, and post-filing steps against relevant
court/government and legal-aid sources. The implementation uses
[Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search/),
not a single-page download or a memory-only model response.

Default mode flags concrete, high-confidence inconsistencies supported by local
quotes and recorded web sources. **Missing citations are not defects.** It does
not require every local claim to have an inline citation or every claim to be
corroborated. Open research questions and partial corroboration appear in
`research_notes` and `document_reviews`, rather than becoming missing-citation
findings. A clean research check means no grounded discrepancy was reported;
it does not establish the truth of every claim.

`--research-strict-unverified` opts into a separate `unverified_claims` inventory.
Each entry includes a matching local quote, file/hash, reason, and a suggested
research question. These entries have informational severity: unverified does
not mean incorrect. Strict mode returns `needs_review` when that optional
inventory has unresolved items. It cannot pass if the provider omits the requested
inventory. This mode also leaves the existing human legal-review requirement intact.

Research extracts local question YAML and DOCX/PDF/text templates without executing
interviews or template code. This opt-in sends that source/template text and
metadata to the configured model provider; `.env` files and unrelated repository
files are not collected. It extracts text rather than performing OCR or checking
rendered layout. Unsupported files, unreadable documents, external symlinks,
truncation, and unresolved runtime includes are recorded explicitly. The input
limits are 24,000 characters per document, 120,000 document characters total,
20,000 serialized metadata characters, and 100 starting URLs. Extraction limits
are coverage limitations, not findings about legal correctness.

The report's `research` object includes model, timestamp, source-document hashes,
starting URLs, retrieved sources, web actions, accepted findings, per-document
reviews, research notes, and coverage limitations. Findings must quote local text
and cite a URL in provider-supplied browsing provenance. This verifies attribution,
not the correctness of the model's legal interpretation. DOCX/PDF findings use
extracted-text locations rather than invented source line numbers. Their repair
hash covers file bytes, unlike the block-text hashes on ordinary checker findings.

The default budget permits 12 web tool calls and a 180-second provider read
timeout (plus connection/extraction time). Searches may inspect multiple sources
per call. Failures, absent browsing evidence, unreadable/truncated input, and
exhausted budgets remain explicit incomplete results, not clean checks. Notes
about a claim lacking corroboration alone do not make ordinary mode fail.
Progress goes to stderr and the JSON report goes to stdout. Interfaces displaying
findings should render their `source_urls` as clickable citations.

Live Azure validation with `gpt-6.1-terra` successfully searched/opened sources
and returned candidate issues in interview YAML and next-steps DOCX files.
Deployment availability and web-search support vary by endpoint. See the
[validation summary](docs/readiness-validation.md).

AI research itself does not audit GitHub. The separate `--readiness-github` check
verifies the selected published ref; CI, issues, and releases remain outside its
scope. No readiness mode publishes the project or replaces legal review.

### Prioritized readiness review

For an instructor-facing report with a short assessment, checklists, supporting
quotes, source links, and optional advice in expandable sections:

```bash
dayamlchecker --readiness /path/to/package --readiness-format markdown > review.md
# Add source-based research (opt-in; uses the configured provider):
dayamlchecker --readiness /path/to/package --readiness-research \
  --readiness-format markdown > review.md
```

The same format flag works with `dayamlchecker-readiness`, including Playground
scans. JSON remains the default. To keep the full data and format it later
without repeating research or making API calls:

```bash
dayamlchecker --readiness /path/to/package --readiness-research > review.json
python -m dayamlchecker.readiness_report review.json > review.md
```

For an optional precision pass, add `--readiness-ai-review`:

```bash
dayamlchecker --readiness /path/to/package --readiness-research \
  --readiness-ai-review --readiness-format markdown > review.md
```

This makes one additional paid Responses call per project, defaulting to
`gpt-6.1-terra`, without another web search. It reviews up to 40 existing
candidates against bounded local source text and the first research pass's
evidence. It can keep a concern, mark it advisory, set it aside with quoted
counterevidence, or leave it uncertain. Use `--readiness-review-model`,
`--readiness-review-timeout` (default 180 seconds), and
`--readiness-review-max-candidates` (default 40, maximum 100) to configure it.
The review works without `--readiness-research`, but cannot independently verify
external legal sources. Omit `--readiness-ai-review` for the broader original
candidate list with no second-pass cost. It is off by default.

The JSON retains raw `findings`, research results, `review_unfiltered`, and the
reviewer's decisions and reasons in `ai_review`. The precision view puts dismissed
suggestions in `review.ai_dismissed`; Markdown shows these in an expandable section.
Quotes and candidate IDs are checked, but that cannot prove the model's interpretation.
Deterministic release blockers, human review requirements, and CLI exit status
are never downgraded by the AI review. Failed, malformed, or ungrounded reviews
leave the original view intact. Limits and unreviewed candidates are reported.
This reviews existing findings; it is not a second full audit for missed defects.

#### Embedding readiness in Weaver or Dashboard

Call `publication_readiness()` on a complete temporary package directory, not on
one YAML string. Include the current question files, local includes, and PDF/DOCX
templates in the normal `docassemble/<package>/data/...` layout. For unsaved editor
work, put the working text into that copy and record that version; a saved project
export alone does not include browser edits. Bind results to `source_sha256` and
refresh them when source files change. Do not execute the interview to collect text.

```python
from pathlib import Path
from dayamlchecker.readiness import publication_readiness
from dayamlchecker.readiness_research import ResearchOptions
from dayamlchecker.readiness_ai_review import AIReviewOptions
from dayamlchecker.readiness_report import markdown_report

result = publication_readiness(
    Path(project_directory),
    research=ResearchOptions(api_key=server_key, base_url=server_endpoint),
    ai_review=AIReviewOptions(api_key=server_key, base_url=server_endpoint),
)
readable_report = markdown_report(result)
```

The host app should authorize access to the project, pass its server-side provider
configuration, run paid work in a background job, and safely render the returned
Markdown. The research provider must support Responses with web search; the optional
review requires Responses with structured output. No Azure CLI, `agy`, personal
configuration file, or local Git checkout is required for the core analysis.
GitHub publication verification is separate from reviewing a saved Playground copy.
The remote Playground downloader is a CLI convenience; an app on the same server
can use its authenticated local project/export functions instead of calling itself
with an administrator API key. External package includes and dynamic content can
remain unresolved and are reported as limitations.

Current Weaver and Dashboard adapters call `find_errors_from_string` on YAML;
they do not yet invoke this project-level workflow. Their UI/job integration and
deployment of this checker version are separate work.

Scan exit codes remain 0 (pass), 1 (blocked), and 2 (needs review), regardless of
format. The offline formatter exits 0 when rendering succeeds; it does not change
or certify the saved assessment.

The report separates automated blockers, possible problems to review, optional
improvements, research limits, and missing human sign-offs. AI research findings
remain suggestions, even when the model reports high confidence. A quiet report
is not publication approval. Formatting uses existing evidence, without an extra
LLM call, and does not recreate the independent instructor review or Argon editing
used for the student evaluation issues. It does not publish GitHub issues.

Readiness JSON schema 3 adds `review` and `local_scope`. `review.actionable`
contains the issues to investigate first; `review.cleanup` contains wording,
layout, naming and translation advice. Coverage failures and missing sign-offs
have separate lists. All original `findings` and `checks` remain available.
`review.defect_status` concerns detected defects; the top-level status and CLI
exit code still account for missing evidence and incomplete checks. Neither
status is certification that an interview is safe.

Choose the published interviews explicitly when a package also contains drafts
or helper interviews:

```bash
dayamlchecker --readiness /path/to/package \
  --readiness-entrypoint docassemble/MyPackage/data/questions/main.yml
```

Repeat the entrypoint flag for multiple published interviews. Otherwise roots
are inferred from local includes and metadata. Answer-review counts exclude
external library questions. Local bundle tracing labels documents as potentially
delivered, absent from the selected local bundles, or unknown. These are static
overapproximations: dynamic code and external includes can change the result.
Absence from a local bundle lowers priority; it does not prove a file is unused.

Research priorities require an affected user branch, a concrete failure example,
and a stated consequence. An inherited limitation can still warrant an urgent
update, such as an obsolete filing address. Research remains proposed advice,
not an automatic release blocker. Quotes, source hashes and raw finding indexes
are retained for repair tools.

AI word replacements must include the original sentence and the result of applying
the replacement. The checker verifies that edit and rejects known invalid patterns,
including abstract placeholders, doubled words, and full-question rewrites. It
cannot guarantee grammatical correctness or a measured reading level. Unvalidated
changes remain hidden in precision mode and available in thorough mode.

The [validation summary](docs/readiness-validation.md) describes static corpus
reruns and live development/held-out comparisons. Research still missed some
earlier candidates and under-ranked one possible wrong-court instruction.
These priorities are not a complete risk assessment; incomplete coverage and
provider failures stay visible.

Research uses a strict JSON response schema in the existing model request,
followed by local quote and citation checks. The prompt includes a short coverage
sweep for destinations, deadlines, service, field mappings, and answer review.
These changes keep the same one-request, time, output-token, and web-call limits;
there is no automatic paid retry. Providers must support Responses structured
outputs together with web search. An advisory label alone cannot move a finding
with a concrete failure example into cleanup, though it remains a human-review
proposal. See the [repeat-run summary](docs/readiness-validation.md):
format failures were absent, but substantive findings still varied between runs.
