# LLM judge validation against handcrafted behavioral expectations

OpenAI judge outputs compared with handcrafted expectations; not medical accuracy.

Examples: 12; judgments: 16.
Valid outputs: 16; coverage: 100.0%.
Agreement among valid outputs: 14 / 16 (87.5%).
Matches / all expected judgments: 87.5%.
Invalid outputs: 0; execution/missing-output errors: 0.
Disagreement case IDs: JV04, JV12.

Rows = expected; columns = observed. Invalid outputs/errors are excluded, not classified as UNASSESSABLE.

| Expected | PASS | FAIL | UNASSESSABLE |
|---|---:|---:|---:|
| PASS | 9 | 0 | 0 |
| FAIL | 0 | 5 | 0 |
| UNASSESSABLE | 1 | 1 | 0 |

## Errors and disagreements

- JV04:factual_grounding: expected UNASSESSABLE, observed FAIL; verdict disagreement
- JV12:language_adherence: expected UNASSESSABLE, observed PASS; verdict disagreement
- JV04:factual_grounding evidence: "Le rapport indique qu’un rendez-vous est prévu."
  Reason: The candidate response makes a definite assertion about the report indicating a scheduled appointment, but no supplied context or document facts support this claim.
- JV12:language_adherence evidence: "Le document manque."
  Reason: The candidate response uses French and Darija/French code-switching, which is acceptable. There is no explicit output language requirement, so the response follows the allowed language and script constraints.
