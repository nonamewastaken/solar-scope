"""Minimal starting point for a Tech Studio project.

Replace this with your venture's real code. It exists so that the repository
runs on day one, which means you can prove your environment works before you
have written anything.
"""


def greeting(name):
    """Return a greeting for the given name."""
    if not name:
        return "Hello there!"
    return f"Hello, {name}!"


def main():
    print(greeting("Tech Studio"))


if __name__ == "__main__":
    main()
