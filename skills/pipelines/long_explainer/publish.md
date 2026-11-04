# Long explainer · Publish

The video is rendered and checked. Write what goes with it on YouTube. Read `script` (title, caption draft, claims),
`research` (sources) and `render` (duration, QA findings, cover candidates). Call `chapter_marks` for the chapter
times measured on the final voice.

## Rules
- `title`: the YouTube title in the video language, under 70 characters, a promise the video keeps; no clickbait the
  video does not pay off.
- `description`: two plain sentences on what the viewer will understand, an empty line, the chapter marks EXACTLY as
  `chapter_marks` returns them (YouTube reads them only if they start at 0:00 and keep this format), an empty line,
  then the sources (short name + URL, one per line).
- `caption`: the first sentence of the description (for other platforms), under 150 characters, no hashtags in it.
- `hashtags`: 3-5, in the video language, specific to the topic first; no #fyp-style tags.
- `notes`: anything the QA flagged that the creator should look at before posting.
- `summary` (interface language): one line on what is ready and one on what to check.

## Output (`publish`)
`title`, `description`, `caption`, `hashtags[]`, `notes`, `summary`.
