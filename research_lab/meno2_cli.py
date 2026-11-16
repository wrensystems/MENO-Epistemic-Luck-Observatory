"""Local MENO commands; all model invocations still use research_lab.engine."""
import argparse
import json
from .storage import read_json
from .meno2_campaign import create_campaign, plan_campaign, run_campaign, inspect_campaign, export_campaign


def main(argv):
    parser = argparse.ArgumentParser(prog='python -m meno')
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('create', help='Freeze an offline campaign specification')
    create.add_argument('directory')
    create.add_argument('--config', help='JSON configuration; omitted uses a synthetic pilot')
    for name in ('suite-create', 'suite-run', 'suite-analyze', 'suite-export'):
        child = sub.add_parser(name)
        child.add_argument('directory')
        if name == 'suite-create': child.add_argument('--config', required=True)
        if name == 'suite-run': child.add_argument('--live', action='store_true')
        if name == 'suite-export':
            child.add_argument('destination')
            child.add_argument('--reviewed-public', action='store_true')
    for name in ('plan', 'verify', 'analyze', 'status', 'run', 'serve', 'export'):
        child = sub.add_parser(name)
        child.add_argument('directory')
        if name == 'run':
            child.add_argument('--live', action='store_true')
        if name == 'serve':
            child.add_argument('--port', type=int, default=8792)
        if name == 'export':
            child.add_argument('destination')
            child.add_argument('--reviewed-public', action='store_true')
    args = parser.parse_args(argv)
    if args.action.startswith('suite-'):
        from .meno2_suite import create_suite, run_suite, inspect_suite, export_suite
        if args.action == 'suite-create':
            config = read_json(args.config)
            result = create_suite(args.directory, config['configurations'], config['cap_usd'], config.get('metadata'))
        elif args.action == 'suite-run': result = run_suite(args.directory, args.live)
        elif args.action == 'suite-export': result = export_suite(args.directory,args.destination,args.reviewed_public)
        else: result = inspect_suite(args.directory)
    elif args.action == 'create':
        result = create_campaign(args.directory, read_json(args.config) if args.config else None)
    elif args.action == 'plan':
        result = plan_campaign(args.directory)
    elif args.action == 'run':
        result = run_campaign(args.directory, args.live)['status']
    elif args.action == 'serve':
        from .meno2_observatory import serve
        serve(args.directory, args.port)
        return 0
    elif args.action == 'export':
        result = export_campaign(args.directory, args.destination, args.reviewed_public)
    else:
        report = inspect_campaign(args.directory)
        result = report['analysis'] if args.action == 'analyze' else report['status']
    print(json.dumps(result, indent=2, allow_nan=False))
    if args.action == 'suite-run':
        return 3 if result['stop_reason'] == 'operational_failure' else 0
    return 3 if args.action == 'run' and result['status'] != 'complete' else 0
