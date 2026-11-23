import argparse
import sys
from slopcheck import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slopcheck",
        description="A minimal code quality CLI tool.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)
    print("slopcheck 0.1.0 is ready!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
