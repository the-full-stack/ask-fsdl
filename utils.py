"""Some simple utilities for the project."""


def pretty_log(str):
    print(f"{START}🥞: {str}{END}")


# Terminal codes for pretty-printing.
START, END = "\033[1;38;5;214m", "\033[0m"
