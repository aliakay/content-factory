# Explainer · Publish

## Hard limits (the gate refuses these)
- `credits` is the `attribution` tool's block verbatim; no asset without a licence reaches the description.
- Caption in the video's language, under 150 characters, ending with a question; 3-5 hashtags.
- These are measured by code at review: an output that meets them is not sent to a model reviewer at all.


The video is rendered and checked. Write what goes with it when the creator posts it. `script` (title, caption
draft, claims), `research` (sources) and `render` (duration, QA findings, cover candidates) are embedded in the task.

## Rules
- `caption`: one or two sentences in the video language, under 150 characters, that add to the video instead of
  repeating line 1, ending with a question the viewer can answer in a word. No hashtags inside it.
- `hashtags`: 3-5, in the video language, specific to the topic first (#DoğalGaz before #Ekonomi); no #fyp-style tags.
- `notes`: the sources to cite in the description (short names + URLs), and anything the QA flagged that the creator
  should look at before posting.
- `summary` (interface language): one line on what is ready and one on what to check.

## Output (`publish`)
`caption`, `hashtags[]`, `notes`, `credits` (the `attribution` tool's `block`, verbatim), `summary`.

{{include:factory.licence:brief}}
