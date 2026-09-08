# Environment Setup

Getting Python, VS Code, and Git working on your machine. Follow the section
for your operating system. If you get stuck, stop and ask a facilitator rather
than fighting it alone. Setup problems are the least interesting part of the
program and we would rather unblock you fast.

## What you need

1. **Python 3.11 or newer**
2. **VS Code**, the editor we demo in and support
3. **Git**
4. A **GitHub account**, set up in Week 1

---

## macOS

**Python.** macOS ships with an old Python that you should not use. Install a
current one from [python.org/downloads](https://www.python.org/downloads/), or
with Homebrew if you already have it:

```
brew install python
```

Check it:

```
python3 --version
```

You want 3.11 or higher.

**Git.** Usually already there. Check with `git --version`. If it is missing,
macOS will offer to install the developer tools. Accept.

**VS Code.** Download from
[code.visualstudio.com](https://code.visualstudio.com/), drag it to
Applications, open it, and install the **Python** extension when prompted.

---

## Windows

**Python.** Install from
[python.org/downloads](https://www.python.org/downloads/). On the first screen
of the installer, tick **"Add python.exe to PATH"** before clicking install.
This one checkbox causes most of the setup problems we see.

Check it in PowerShell:

```
python --version
```

**Git.** Install [Git for Windows](https://git-scm.com/download/win). The
defaults are fine.

**VS Code.** Download from
[code.visualstudio.com](https://code.visualstudio.com/) and install the
**Python** extension when prompted.

**If PowerShell refuses to run the setup script**, it is blocking local
scripts. Run this once, then try again:

```
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## Then, for any project

From inside the project folder:

**macOS**

```
bash setup.sh
source .venv/bin/activate
```

**Windows**

```
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`. That means the virtual
environment is active and anything you install goes into this project rather
than your whole machine. You activate it every time you open a new terminal.

Check the project runs:

```
python src/app.py
pytest
```

A greeting and passing tests mean you are ready.

---

## Why a virtual environment

Different projects need different versions of the same library. A virtual
environment gives each project its own private set, so installing something for
one project cannot break another. The `.venv` folder is where they live, and it
is in `.gitignore` because it is rebuilt from `requirements.txt` rather than
shared. That is why teammates run the setup script instead of you sending them
your folder.

## Common problems

**`python: command not found` on Windows.** The PATH checkbox was missed during
install. Re-run the installer and choose Modify, or reinstall with the box
ticked.

**`pip: command not found` after activating.** Use `python -m pip` instead.

**Changes are not taking effect.** Check your prompt shows `(.venv)`. A new
terminal window does not inherit it.

**Anything else.** Bring it to the session. This is what the Do hour and office
hours are for, and someone else in the room has almost certainly hit the same
thing.
