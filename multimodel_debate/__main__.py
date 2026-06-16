"""Enable `python -m multimodel_debate "your prompt" [flags]`."""

from .debate import main

if __name__ == "__main__":
    raise SystemExit(main())
