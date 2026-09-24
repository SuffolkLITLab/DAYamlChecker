`x_documents_anonymized.yml` and `x_review_anonymized.yml` are the unmodified
examples shared by @jpagh in
https://github.com/SuffolkLITLab/DAYamlChecker/pull/89#issuecomment-5778835599.

Original attachments:
- https://github.com/user-attachments/files/32524216/x_documents_anonymized.yml
- https://github.com/user-attachments/files/32524217/x_review_anonymized.yml

The documents example depends on server configuration, unavailable offline.
Its config-driven include loop renders empty; its two ordinary question blocks
still produce EG414 (missing question IDs). The review example expands local
macros while preserving Mako expressions and produces no findings.
