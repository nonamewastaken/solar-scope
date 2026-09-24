# Reference Project

This is the project your facilitators build **live, in front of you, every week**.

During the first hour of each session, the Show hour, a facilitator works on
this repository: scoping a problem, using AI and pushing back on what it
produces, making decisions out loud, and writing the code. You watch the whole
workflow rather than a finished result. Then in the second hour you apply the
same idea to your own venture project.

Everything here is public and stays public. Read it, clone it, copy patterns
out of it. That is what it is for.

## What it is not

It is not the answer key to your project. Your venture is different, and
copying this code will not fit it. What transfers is the approach: how the
problem got broken down, why a piece was built the way it was, and where the
builder decided the AI was wrong.

## How to follow along

```
git clone https://github.com/ub-tech-studio/reference-project.git
cd reference-project
```

Then, with [uv](https://docs.astral.sh/uv/) installed from the pre-work:

```
uv sync
uv run main.py
```

If you see a greeting and `Python 3.14.7 is ready to build.`, your
environment works.

Each week's work lands here after the session, so you can read back over
anything that went past too quickly in the room.

## Status

The project subject is being finalised and lands here before Week 2 on
September 17, which is the first session with a Show hour. Week 1 is
orientation, team formation, and account setup, so there is nothing you need
from this repository on day one.

The skeleton is already in place: a uv project pinned to Python 3.14.7, a
`.gitignore`, a starter `main.py` that runs, the four `docs/` files every team
fills in, and a pull request template. Same starting point your team
repository gets from
[tech-studio-starter](https://github.com/ub-tech-studio/tech-studio-starter).
