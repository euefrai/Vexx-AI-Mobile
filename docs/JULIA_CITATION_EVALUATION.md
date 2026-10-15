# Citation evaluation

`citation_stage_metrics` reports four independent, explicitly annotated
stages:

1. `citation_exists`: the citation identifier/reference is present.
2. `source_retrieved`: the cited source was actually obtained by the run.
3. `passage_found`: the cited passage exists in that source.
4. `claim_supported`: an independent reviewer/reference label says the
   passage supports the claim.

The stage rates use the number of reviewed citation records as the denominator.
An empty evaluation returns `null` rates rather than a success-shaped zero.
Passing an earlier stage never implies passing a later one.

The current local retrieval benchmark does not emit claim-support judgments.
The metrics helper must receive those labels from reviewed fixtures; it does
not compare meaning, infer support, or call a live model. Structural citation
validation in report generation is not a semantic citation-quality score.
