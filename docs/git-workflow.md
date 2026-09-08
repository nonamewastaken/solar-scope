# Git Workflow

One page. This is the loop you will repeat all semester.

## Once per machine

Tell Git who you are. Use the same email as your GitHub account.

```
git config --global user.name "Your Name"
git config --global user.email "you@buffalo.edu"
```

## Once per project

Copy the repository onto your machine.

```
git clone <the repository URL>
cd <the project folder>
```

## Every time you work

**1. Start from an up to date main.**

```
git checkout main
git pull
```

**2. Make a branch for what you are about to do.** Name it after the work, not
after yourself.

```
git checkout -b add-login-form
```

**3. Do the work.** Then see what you changed.

```
git status
git diff
```

**4. Commit it.** Stage the files you meant to change, not everything blindly.

```
git add src/app.py
git commit -m "Add the login form"
```

Write the message so a teammate reading it in three weeks knows what happened.
"Fixed stuff" tells them nothing.

**5. Push the branch.**

```
git push -u origin add-login-form
```

**6. Open a pull request** on GitHub. Describe what you did and why. Ask a
teammate to review it.

**7. Review, merge, and clean up.** Once it is approved and merged:

```
git checkout main
git pull
git branch -d add-login-form
```

Then start again from step 1.

## When something goes wrong

**I committed to main by accident.** Do not panic, nothing is lost.
Ask a facilitator, this is a two minute fix.

**Someone else changed the same file.** Git will say there is a conflict. Open
the file, you will see both versions marked. Pick what is correct, delete the
markers, then commit. Ask for help the first time, it is much easier shown than
read.

**I do not know what state I am in.** `git status` almost always tells you, and
it usually suggests the command you want next. Read it before you guess.

## The rule that matters most

Commit often and push often. Work that only exists on your laptop is work your
team cannot see, cannot review, and cannot recover if your laptop dies.
