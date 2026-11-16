"""Thin public wrapper; scientific execution remains in the preserved engine."""
import sys

from research_lab.meno2_cli import main
from research_lab.providers import ProviderError


try:
    raise SystemExit(main(sys.argv[1:]))
except (ValueError, OSError, KeyError, TypeError, ProviderError) as exc:
    print(f'Error: {exc}', file=sys.stderr)
    raise SystemExit(2)
except KeyboardInterrupt:
    print('Interrupted. Preserve the campaign and inspect uncertain attempts before resuming.',
          file=sys.stderr)
    raise SystemExit(130)

