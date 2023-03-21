#!/usr/bin/env python3
import argparse
import logging
import os
import subprocess
import sys
import time

STATS = {
    'cpu': {'column':2, 'type':float},
    'mem': {'column':3, 'type':float},
    'vsz': {'column':4, 'type':int},
    'rss': {'column':5, 'type':int}
}
DESCRIPTION = """Monitor the resource usage of a process or set of processes over their run time."""


def make_argparser():
    parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
    options = parser.add_argument_group('Options')
    options.add_argument('query', nargs='+',
        help='Query to match against the command line. This does a simple, exact match against the '
            'full command line. If the query is a substring of the command line, it\'s a match. '
            'Note that you can give a single argument with spaces or multiple arguments. If the '
            'command isn\'t running yet, this will wait until it appears.')
    options.add_argument('-m', '--me', action='store_true',
        help='Restrict search to my processes (the current user).')
    options.add_argument('-u', '--user',
        help='Restrict search to this user.')
    options.add_argument('-p', '--pause', type=int, default=5,
        help='Seconds to pause between polling.')
    options.add_argument('-h', '--help', action='help',
        help='Print this argument help text and exit.')
    logs = parser.add_argument_group('Logging')
    logs.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
        help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
    volume = logs.add_mutually_exclusive_group()
    volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
        default=logging.WARNING)
    volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
    volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
    return parser


def main(argv):

    parser = make_argparser()
    args = parser.parse_args(argv[1:])

    logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

    query = ' '.join(args.query)

    if args.me:
        command = ('ps', 'ux')
    else:
        command = ('ps', 'aux')

    waiting = True
    while True:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        num_procs, stats = get_stats(process.stdout, query, args.user)
        if num_procs == 0:
            if waiting:
                time.sleep(args.pause)
                continue
            else:
                break
        waiting = False
        ordered_stats = sorted(stats.items(), key=lambda item: STATS[item[0]]['column'])
        output = [round(time.time()), num_procs] + [str(value) for stat, value in ordered_stats]
        print(*output, sep='\t')
        time.sleep(args.pause)


def get_stats(lines, query, user):
    # Init the total for each stat to zero.
    totals = {}
    for stat, meta in STATS.items():
        totals[stat] = meta['type']()

    # Add up the stats.
    num_procs = 0
    for fields in filter_ps(lines, query, user):
        num_procs += 1
        for stat, meta in STATS.items():
            raw_value = fields[meta['column']]
            value = meta['type'](raw_value)
            totals[stat] += value

    return num_procs, totals


def filter_ps(lines, query, user):
    our_pid = str(os.getpid())
    header = True
    for line_raw in lines:
        if header:
            header = False
            continue
        fields = line_raw.rstrip('\r\n').split()
        user = fields[0]
        if user is not None and user != user:
            continue
        pid = fields[1]
        if pid == our_pid:
            continue
        command_line = ' '.join(fields[10:])
        if query in command_line:
            yield fields


def fail(message):
    logging.critical(f'Error: {message}')
    if __name__ == '__main__':
        sys.exit(1)
    else:
        raise RuntimeError(message)


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except (BrokenPipeError, KeyboardInterrupt):
        pass
