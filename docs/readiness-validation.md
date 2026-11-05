# Publication-readiness validation

This feature supports an instructor or maintainer reviewing an interview for
minimum publication safety: useful compared with the original PDF, without
clear added errors. It does not certify legal accuracy, execute interviews, or
publish them. All counts below describe development evaluations on November 5,
2026; they are not measured precision or recall scores.

## Evaluation coverage

- Initial style evaluation: 18 repositories and 50 YAML files. Candidate findings
  fell from 916 to 622 after precision changes. A reduction alone does not prove
  that the removed findings were wrong.
- Broader exploration: 54 repositories, plus live development and held-out
  comparisons. Research sometimes missed previously observed concerns and
  under-ranked a possible wrong-court instruction.
- Student validation: 11 repositories, comparing GitHub files with selected
  recent Playground projects and independently inspecting instructions, review
  paths, and attachment mappings. Five had different interview/template files
  in Playground. Sixteen bounded research calls produced 13 incomplete results
  and three failures. Incomplete results could still contain useful findings.
- Final static regression comparison: 65 repositories with unchanged source
  fingerprints. Eight false alerts were removed and one mixed review-editing
  warning was narrowed. No new alerts or readiness-status changes resulted.
  Paired tests retain warnings for nearby genuine problems.
- Four repeated live research calls after structured-output improvements had no
  response-format failures, but substantive findings varied between runs.
- Three live optional AI second-opinion trials took approximately 9–11 seconds
  each. They retained a revocation-instructions concern, left an edit-path
  question uncertain, and dismissed a known missing-exit false positive.
  A historical numeric-choice false positive was merely marked advisory rather
  than dismissed. This is a small development sample, not a benchmark.

The second opinion uses one additional call, without web tools or automatic
retries. The three trials used about 6,900–16,900 input tokens and 1,000–1,250
output tokens each. Pricing depends on the deployment. Early recommendations
included runtime testing; the prompt now limits recommendations to static
inspection or explicit uncertainty. A quoted passage does not prove that the
model interpreted it correctly.

## What the evaluations changed

- Recognize generated name fields and separate date/location inputs before
  alleging vague or compound questions.
- Avoid unconfirmed plain-language replacements; validate the proposed edit in
  its sentence and preserve candidate details for broader editorial review.
- Recognize local rejection screens and numeric choice values.
- Follow review links into editable tables without assuming that one edit link
  makes every answer editable.
- Separate optional polish, research proposals, coverage gaps, and missing human
  sign-offs from concrete automated release blockers.
- Preserve source excerpts, references, raw findings, and reviewer decisions so
  a person can accept or dispute each finding.

## Known gaps

Independent review found problems that automated passes missed, including an
attachment Mako compilation error, wrong PDF field mappings, and extra people
accepted by review screens but omitted from the finished form. The syntax gap
is tracked in [issue #101](https://github.com/SuffolkLITLab/DAYamlChecker/issues/101)
and is not fixed by this feature. Template mapping and list-capacity checks need
further work. External package includes and dynamic paths can remain unresolved.

A quiet scan is not publication approval. AI findings remain proposals; AI review
cannot downgrade deterministic blockers or satisfy human sign-offs. Failed or
ungrounded review responses preserve the original findings. Source changes
invalidate supplied review evidence. Weaver and Dashboard still need adapters
that provide complete project files and run the work in background jobs.

Raw project reports, student review exports, provider responses, and machine-
specific evaluation files are intentionally excluded from this change. Regression
fixtures use small synthetic examples rather than copying student projects.
