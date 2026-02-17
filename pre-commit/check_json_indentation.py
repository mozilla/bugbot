#!/usr/bin/env python3
import sys


def check_json_indentation(filename):
    with open(filename, "r") as file:
        lines = file.readlines()

    tabs_found = False
    spaces_found = False

    for line in lines:
        stripped_line = line.lstrip()
        if stripped_line and line.startswith("\t"):
            tabs_found = True
        elif stripped_line and line.startswith(" "):
            spaces_found = True

        if tabs_found and spaces_found:
            print(f"Error: {filename} contains mixed tabs and spaces for indentation.")
            return False

    return True


if __name__ == "__main__":
    files_to_check = sys.argv[1:]
    exit_code = 0

    for json_file in files_to_check:
        if not check_json_indentation(json_file):
            exit_code = 1

    sys.exit(exit_code)
