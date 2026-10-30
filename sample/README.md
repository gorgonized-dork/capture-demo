# sample/

Everything in this folder is fictional. The Harrowmere Valley Library
District, its branches, and every event and figure in these files are
invented for testing. They describe no real place, organization, or person.

- `brief.json`: a research brief, the hypothesis the sample run tests.
- `items.json`: ten short source items, read by the fixture adapter.

The items are written to exercise the pipeline, not to prove the hypothesis.
Some support it, one contradicts it, and one reports a branch whose hours
did not change. One falls outside the brief's date range, one matches an
exclude term, one is off-topic, and one republishes another item's facts.
One claims a rise but gives no figures, and two leave `unit` (one also
`region`) empty. Two ids, `fx-1001` and `fx-10010`, differ only by a
trailing digit, so ID matching can be tested as exact.

These files are test fixtures: they change only with explicit approval.
