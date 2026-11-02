"""Command line entry point: python -m ferro_parking <command> [options]

Commands:
  match   Stage 1: match sheet rows to OpenStreetMap and pick a research route
"""
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, argv = sys.argv[1], sys.argv[2:]
    if cmd == "match":
        from .osm_match import main as match_main
        return match_main(argv)
    print(f"Unknown command: {cmd}\n\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
