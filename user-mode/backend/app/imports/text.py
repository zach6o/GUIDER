"""Turning a pasted transcript into a proposal, and refusing what it asserts.

Two separate jobs, and the order matters. `extract_locally` is the deterministic
importer: it reads structure the user can see for themselves — numbered steps,
a first question — and invents nothing. `vet_import` is the guard for this
surface: whatever produced the proposal, a transcript cannot talk its way into
the goal or the steps.

The extracted steps still go through `step_policy` when they are persisted, like
any other proposed step, so a restricted action is marked `block` and can never
produce an instruction. What is added here is the injection check: text that
addresses Guider rather than describing the user's task is removed before it can
be carried forward as context.
"""

import re

from app.errors import GuideError
from app.providers.base import ImportContext, ImportedTask, ProposedPlan, ProposedStep

# Text that claims authority it does not have. Matched against the goal and each
# step's directive fields. This is deliberately about *form*, not topic: a
# transcript may legitimately discuss system prompts; a step may not issue one.
INJECTION = re.compile(
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|earlier|above)\s+"
    r"(instructions?|messages?|rules?|prompts?)"
    r"|disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|earlier|above)"
    r"|you\s+are\s+now\s+"
    r"|from\s+now\s+on[,:]?\s+you"
    r"|(^|\n)\s*(system|developer|assistant)\s*:"
    r"|<\|?im_(start|end)\|?>"
    r"|\[\s*(system|developer)\s+(prompt|message)\s*\]"
    r"|act\s+as\s+(the\s+)?(system|developer|guider)"
    r"|new\s+instructions?\s*:"
    r"|override\s+(your|the)\s+(policy|rules|instructions)",
    re.IGNORECASE,
)

STEP_MARKER = re.compile(r"^\s*(?:step\s*)?(?:\d{1,2})[.)]\s+(?P<text>\S.*)$", re.IGNORECASE)
BULLET = re.compile(r"^\s*[-*•]\s+(?P<text>\S.*)$")
SPEAKER = re.compile(
    r"^\s*(you|user|me|human|assistant|chatgpt|claude|gemini)\s*:\s*", re.IGNORECASE
)
MAX_STEPS = 12


def looks_like_injection(*texts: str) -> bool:
    return any(INJECTION.search(text or "") for text in texts)


def strip_injection(text: str) -> str:
    """Remove sentences that address Guider rather than describe the task."""
    kept = [
        line for line in text.splitlines() if line.strip() and not INJECTION.search(line)
    ]
    return " ".join(" ".join(kept).split())[:4000]


def first_question(transcript: str) -> str:
    """The user's own opening line, which is the closest thing a transcript has
    to a goal. Speaker labels are removed; nothing is invented.

    A line that addresses Guider is skipped rather than taken as the goal: an
    injection placed above the real question must not decide what the task is,
    and must not be able to leave the user with no goal at all.
    """
    for line in transcript.splitlines():
        clean = SPEAKER.sub("", line).strip()
        if len(clean) < 12 or STEP_MARKER.match(line) or BULLET.match(line):
            continue
        if INJECTION.search(clean):
            continue
        return clean[:4000]
    return ""


def extract_locally(ctx: ImportContext, application_key: str = "unknown") -> ImportedTask:
    """The deterministic importer: structure the user can see, and nothing else.

    It does not summarize, infer intent or fill gaps — a numbered line becomes a
    step with the same words, and the opening line becomes the goal. When a real
    importer role is configured it answers instead; this one is what runs with no
    provider, and it is honest about being a parser rather than a reader.
    """
    lines = ctx.transcript.splitlines()
    steps: list[ProposedStep] = []
    for line in lines:
        match = STEP_MARKER.match(line) or BULLET.match(line)
        if not match:
            continue
        action = " ".join(match.group("text").split())[:1000]
        if len(action) < 8:
            continue
        steps.append(
            ProposedStep(
                title=action[:120],
                action=action,
                expected_result="",
                success_criterion=action[:500],
                fallback="",
                explanation="Taken word for word from the conversation you pasted.",
                application_key=application_key,
                evidence_kind="self_report",
            )
        )
        if len(steps) == MAX_STEPS:
            break

    goal = first_question(ctx.transcript)
    if not steps or not goal:
        raise GuideError(
            422,
            "import_unreadable",
            "Guider could not find a goal and steps in that text. "
            "Paste the part of the conversation with the steps in it.",
        )
    return ImportedTask(
        goal=goal,
        application_key=application_key,
        plan=ProposedPlan(
            assumptions=[
                "Read from the conversation you pasted, word for word. "
                "Nothing here was checked against your screen.",
            ],
            steps=steps,
        ),
    )


def vet_import(result: ImportedTask) -> ImportedTask:
    """The guard for imported text.

    A transcript is data. Anything in it that addresses Guider is removed from the
    goal, and a step whose directive is an injection attempt is dropped outright —
    there is nothing in such a step for a user to review. Restricted *actions* are
    not dropped here: `step_policy` marks them `block` at persist time, so the user
    still sees that the conversation suggested them.
    """
    goal = strip_injection(result.goal)
    if len(goal) < 3:
        raise GuideError(
            422,
            "import_unreadable",
            "That text did not contain a goal Guider can work from.",
        )
    steps = [
        step
        for step in result.plan.steps
        if not looks_like_injection(step.title, step.action, step.fallback)
    ]
    if not steps:
        raise GuideError(
            422,
            "import_unreadable",
            "None of the steps in that text were usable. Paste the steps you want to follow.",
        )
    return ImportedTask(
        goal=goal,
        application_key=result.application_key,
        plan=ProposedPlan(assumptions=result.plan.assumptions, steps=steps[:MAX_STEPS]),
    )
