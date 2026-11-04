# sample/

Everything in this folder is fictional. The Harrowmere Valley Library
District, its branches, and every event and figure in these files are
invented for testing. They describe no real place, organization, or person.

- `brief.json`: a research brief, the hypothesis the sample run tests.
- `items.json`: ten short source items, read by the fixture adapter.
- `proposed_evidence.json`: ten evidence proposals, each a claim with a
  verbatim excerpt and a stance. They are written by hand, standing in for
  an extractor; nothing here extracts evidence automatically.
- `review_log.json`: five review decisions by a fictional reviewer, named
  by role only. The review log is the only thing that can accept or reject
  evidence.

The items are written to exercise the pipeline, not to prove the hypothesis.
Some support it, one contradicts it, and one reports a branch whose hours
did not change. One falls outside the brief's date range, one matches an
exclude term, one is off-topic, and one republishes another item's facts.
One claims a rise but gives no figures, and two leave `unit` (one also
`region`) empty. Two ids, `fx-1001` and `fx-10010`, differ only by a
trailing digit, so ID matching can be tested as exact.

Eight of the proposals are sound. Two are wrong on purpose, to show the
ledger refusing them: EV-009 quotes Northgate's June figure as 1,980 instead
of 1,880, and EV-010 tries to mark itself `ACCEPTED`. The review log accepts
four pieces of evidence, rejects one (a republished report), and leaves
three unreviewed, so they stay `PROPOSED`.

These files are test fixtures: they change only with explicit approval.
