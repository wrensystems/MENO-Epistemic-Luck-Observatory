"""Local research interface operated by Codex under Louis's approvals."""
import argparse
import json
from pathlib import Path
import sys

from .analysis import analyze, write_analysis
from .engine import cost, inspect_run, run, verify
from .providers import ProviderError
from .openai_provider import DEFAULT_OPENAI_MODEL, openai_defaults
from .publication import export_run
from .studies import init_study, load_study, plan


def parser():
    p = argparse.ArgumentParser(prog='research-lab', description='Offline-first research laboratory')
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Initialize an independent draft study with synthetic fixtures')
    init.add_argument('name')
    init.add_argument('--root', type=Path, default=Path.cwd())
    listing = sub.add_parser('list', help='List studies')
    listing.add_argument('--root', type=Path, default=Path.cwd())
    for name in ('validate', 'plan', 'run'):
        child = sub.add_parser(name)
        child.add_argument('study', type=Path)
        if name != 'validate':
            child.add_argument('--mode', choices=['pilot', 'full'], default='pilot')
        if name == 'run':
            child.add_argument('--resume', type=Path)
            child.add_argument('--live', action='store_true', help='Explicitly activate paid model calls after approval')
            child.add_argument('--retry-uncertain', action='store_true', help='Authorize possible duplicate billing after interrupted requests')
    for name in ('verify', 'status', 'analyze', 'export'):
        child = sub.add_parser(name)
        child.add_argument('run_dir', type=Path)
        if name == 'analyze':
            child.add_argument('--out', type=Path)
        if name == 'export':
            child.add_argument('destination', type=Path)
            child.add_argument('--reviewed-public', action='store_true')
    check = sub.add_parser('check-openai', help='Read-only model availability check; no generation')
    check.add_argument('--model', default=DEFAULT_OPENAI_MODEL)
    sub.add_parser('openai-defaults', help='Show default model fields for new studies; no network or spending approval')
    sub.add_parser('meno2', help='Epistemic Luck Observatory (use meno2 --help)')
    return p


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == 'meno2':
        from .meno2_cli import main as meno2_main
        try:
            return meno2_main(arguments[1:])
        except (ValueError, OSError, KeyError, TypeError, ProviderError) as exc:
            print(f'Error: {exc}', file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print('Interrupted. Preserve the campaign and inspect uncertain attempts before resuming.', file=sys.stderr)
            return 130
    args = parser().parse_args(argv)
    try:
        if args.command == 'openai-defaults':
            result = openai_defaults()
        elif args.command == 'check-openai':
            from .openai_provider import OpenAIProvider
            result = {'model': OpenAIProvider().check_model(args.model), 'generation_requests': 0,
                      'billing_verified': False}
        elif args.command == 'init':
            result = {'study_dir': str(init_study(args.root, args.name))}
        elif args.command == 'list':
            result = {'studies': []}
            for directory in sorted((args.root / 'studies').glob('*')):
                if directory.is_dir():
                    config, _ = load_study(directory)
                    result['studies'].append({k: config[k] for k in ('id', 'title', 'protocol_status', 'evidence_kind')})
        elif args.command == 'validate':
            config, cases = load_study(args.study)
            result = {'valid': True, 'study': config['id'], 'cases': len(cases)}
        elif args.command == 'plan':
            config, cases = load_study(args.study)
            tasks = plan(config, cases, args.mode)
            reserve = cost(config, config['max_input_tokens'], config['max_output_tokens'])
            result = {'planned': len(tasks), 'mode': args.mode, 'provider': config['provider'],
                      'model': config['model'],
                      'evidence_kind': config['evidence_kind'], 'max_requests': config['max_requests'],
                      'max_cost_usd': config['max_cost_usd'], 'reserved_per_attempt_usd': str(reserve),
                      'first_pass_reservation_usd': str(reserve * len(tasks)),
                      'tasks': [{k: t[k] for k in ('id', 'case_id', 'condition', 'repetition')} for t in tasks]}
            if config['provider'] == 'openai':
                result['reasoning_effort'] = config.get('reasoning_effort', 'none')
        elif args.command == 'run':
            result = run(args.study, args.mode, args.resume, args.live, args.retry_uncertain)
        elif args.command == 'verify':
            result = verify(args.run_dir)
        elif args.command == 'status':
            result = inspect_run(args.run_dir)
        elif args.command == 'analyze':
            result = write_analysis(args.run_dir, args.out) if args.out else analyze(args.run_dir)
        else:
            result = export_run(args.run_dir, args.destination, args.reviewed_public)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0 if args.command != 'run' or result['status'] == 'complete' else 3
    except (ValueError, OSError, KeyError, TypeError, ProviderError) as exc:
        # Provider errors are sanitized at the HTTP boundary; never print API headers.
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted. Inspect status before resuming; an unsealed call may have been billed.', file=sys.stderr)
        return 130
