"""Motion grammar (t517): what a move MEANS, and a catalogue of explanatory mechanisms.

The motion doctrine (motiondesign.MOTION_DOCTRINE) says how a move should feel; this says what it says. A direction,
a scale change or a colour change is a word: once a video uses it for one meaning it keeps that meaning. And every
explainer scene is built on one mechanism (a known way a picture explains: a chain of causes, a scale comparison, a
before / after, ...) whose beats the motion follows. The scene designer names each scene's mechanism (`mechanism`);
submit_artifact refuses unknown ids and a run of three scenes on the same mechanism, and the reviewer checks the
beats on the stills.
"""

GRAMMAR = """MOTION GRAMMAR (what a move means; binding, one meaning per verb for the whole video):
- Direction is time and cause: left -> right (in RTL scripts right -> left) is "then / because of this"; the next
  step of a process enters from the side time flows from. Going back in time moves the other way, and only then.
- Up is more, down is less: a value that grows rises or grows taller; a loss sinks. Never let a falling number climb.
- Push in is focus (this detail matters now); pull out is context (here is where it sits). A push in must land on
  the thing the voice names; a pull out must reveal something new in the wider frame.
- Scale is magnitude: when two things are compared by size, their sizes are true to the numbers (or the scene says
  it is not to scale). A pop of scale is emphasis and is spent on one thing per scene.
- Colour change is state change: the accent colour means "the point / the new"; a thing that turns accent has
  changed state (true, new, chosen). Red / green only for bad / good or down / up, never as decoration.
- Connection is causation: a line or arrow that draws from A to B claims A leads to B; draw it in the direction of
  the cause, at the moment the voice says it.
- Appearance is assertion, disappearance is dismissal: what leaves the frame is no longer true or no longer the
  subject; keep on screen what the next line builds on.
- Repetition is a rhyme: when an idea returns, its picture returns in the same place, the same colour, the same move.
- Write the video's verbs in `concept` (e.g. "left->right = time, accent = the new rule") and keep them.

CAMERA SPEED AND CUTS (after cinecode's camera vocabulary; numbers, not adjectives):
- Name every camera move as: move, seconds, speed easing, target ("push in, 3 s, slow ease-in-out, on the number").
  Speed words: slow = a subject changes size <= 10 % per second or takes >= 6 s to cross the frame; medium = 10-25 %
  per second, 3-6 s to cross; fast = more than 25 % per second, 1.5-3 s to cross.
- Easing carries meaning: ease-out (fastest at frame 0) opens a hook, ease-in gathers force toward an ending,
  ease-in-out is deliberate and self-contained, linear is for machines. The first scene never starts on an ease-in.
- One primary move per scene, at most one secondary. A move already moving at the cut stays moving into the next scene.
- Cut seams: cut at the move's fastest moment, not as it settles; keep direction and speed the same on both sides
  (a push in keeps pushing in, a pan right meets a pan right); hold the subject's position within a tenth of the frame.
- Adjacent scenes differ in move, size or direction; never the same designed transition twice in a row (a plain cut is
  the default and may repeat). Spend the big ones (freeze, speed ramp, smash cut, dolly zoom) once per video.
- Every cut has a reason you could say aloud: the next step, this caused that, this becomes that, into or out of the
  subject, later, back to an earlier picture changed. A cut with no reason is the one to remove."""

LINES = ("explainer", "long_explainer")            # lines whose scenes must name a mechanism

# id -> (what it explains, the beats setup / action / resolution, the motion, a trap to avoid)
MECHANISMS = {
    "cause_chain": ("why something happens: A leads to B leads to C",
                    "show A alone · draw the link and bring in B, then C, each on its trigger word · the whole chain "
                    "visible, the result in accent",
                    "links draw in the direction of the cause; each new link starts as the previous one lands",
                    "a list of boxes that appear without the links doing the work"),
    "scale_compare": ("how big one thing is next to another",
                      "the familiar thing first, at a size the eye can hold · the other arrives, or the camera pulls "
                      "out until it fits · hold both with the ratio written",
                      "sizes true to the numbers; the camera move IS the comparison",
                      "two numbers side by side with no change of scale"),
    "before_after": ("what changed",
                     "the before state, readable · one transforming move (wipe, morph, a slider) · the after state "
                     "with the difference marked",
                     "the same layout both times so only the change moves",
                     "two unrelated pictures cut together"),
    "build_up": ("how a whole is made of parts",
                 "an empty frame or the first part · parts join one by one on their words · the finished whole, "
                 "then a pull out",
                 "each part enters from where it belongs; the whole settles once",
                 "everything appearing at once"),
    "zoom_detail": ("where a detail sits in the big picture, or what is inside something",
                    "the whole · a push in through the frame to the detail · the detail sharp, the context dimmed",
                    "one continuous push in, not a cut",
                    "a zoom that lands on nothing the voice names"),
    "flow": ("a process or a movement of something (money, gas, people, data)",
             "the source and the target · tokens travel along the path, speed and density meaning volume · the "
             "total arrives at the target",
             "paths draw first, then flow; a change of volume changes the density, not the colour",
             "arrows that never move"),
    "timeline": ("when things happened and in what order",
                 "the axis and the first date · the camera or the axis travels, events drop on their dates · the "
                 "present marked, the trend visible",
                 "time always runs the same way; spacing true to the dates",
                 "dates evenly spaced when they are not"),
    "map_route": ("where: places, routes, borders",
                  "the map at a size that names the region · the route or the area draws, labels appear on arrival "
                  "· the key place in accent",
                  "the camera follows the route; labels never cover the path",
                  "a static map with a pin"),
    "split_compare": ("two options, two sides, two groups",
                      "the two sides with their labels · the same measure animates on both at the same time · the "
                      "winner or the gap marked",
                      "both sides move in sync; the difference is the only asymmetry",
                      "two columns of text"),
    "chart_build": ("a trend or a share in numbers",
                    "axes and the unit · the series draws or the bars grow on the voice · the key value called out",
                    "values from the research, exact; the callout points at the data, not near it",
                    "a chart that is fully drawn before the voice reaches it"),
    "reveal": ("the surprising answer, the twist",
               "a question or a covered thing, held long enough to wonder · one decisive move uncovers it · the "
               "answer big and still",
               "anticipation before the move; nothing else moves during the reveal",
               "a reveal on a scene that has nothing hidden"),
    "metaphor": ("an abstract idea through a concrete picture (a dam for a limit, a funnel for a filter)",
                 "the concrete object, recognisable · it behaves like the idea (the dam fills, overflows) · the "
                 "label ties the picture to the idea",
                 "the object obeys its own physics; the label arrives as the behaviour happens",
                 "a picture that only decorates the words"),
    "count_up": ("one big number and what it means",
                 "the unit and the context · the number counts or stacks up to its value · it lands and is "
                 "compared with something felt",
                 "the count eases out and stops dead on the exact value; the unit stays visible",
                 "a number with no comparison"),
    "hook_question": ("the first second: a question or a claim that stops the scroll",
                      "the strongest picture of the whole video at its first tenth of a second · one move that "
                      "makes it a question · cut on the answer's first word",
                      "already moving at frame 1; no fade from black",
                      "a title card"),
    "cta_end": ("the end: the takeaway and the next step",
                "the takeaway in one line · the call to action enters · hold still for the end card",
                "slower than the rest; everything settles",
                "a new idea in the last scene"),
}


def catalog_text(p=None):
    rows = [f"- {k}: explains {v[0]}. Beats: {v[1]}. Motion: {v[2]}. Trap: {v[3]}." for k, v in MECHANISMS.items()]
    return ("MECHANISM CATALOGUE (each scene names ONE in `mechanism`; its beats are the scene's setup -> action -> "
            "resolution; never three scenes in a row on the same mechanism):\n" + "\n".join(rows))


def brief(p=None):
    return GRAMMAR + "\n\n" + catalog_text(p)


def problems(scenes):
    """What submit_artifact refuses: a scene without a known mechanism, three in a row on one mechanism."""
    out = []
    for i, sc in enumerate(scenes or []):
        m = sc.get("mechanism")
        if not m:
            out.append(f"scene {sc.get('id', i)}: name its `mechanism` (one id of the mechanism catalogue)")
        elif m not in MECHANISMS:
            out.append(f"scene {sc.get('id', i)}: unknown mechanism '{m}'; use one of {', '.join(MECHANISMS)}")
    ms = [sc.get("mechanism") for sc in scenes or []]
    for i in range(len(ms) - 2):
        if ms[i] and ms[i] == ms[i + 1] == ms[i + 2]:
            out.append(f"scenes {i + 1}-{i + 3} all use '{ms[i]}': change the mechanism of the middle one")
            break
    return out
