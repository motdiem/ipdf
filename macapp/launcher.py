"""Entry point used as the py2app application script.

Kept as a tiny standalone module (rather than ``-m macapp``) because py2app
bundles a single start-up script.
"""

from macapp.app import main

if __name__ == "__main__":
    main()
