#!/usr/bin/env python3
import argparse
import collections
import logging
import pathlib
import random
import subprocess
import sys
import accountslib
assert sys.version_info.major >= 3, 'Python 3 required'

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DESCRIPTION = """Generate random names. Omit ones I've already used in online accounts."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  parser.add_argument('num_names', type=int, default=10, nargs='?',
    help='Choose and print this many names. Default: %(default)s')
  parser.add_argument('accounts', metavar='accounts.txt', nargs='?', type=pathlib.Path,
    default=pathlib.Path('~/annex/Info/reference, notes/accounts.txt').expanduser(),
    help='The accounts text file. Default: %(default)s.')
  parser.add_argument('-u', '--print-used', action='store_true',
    help='Just print a list of all names already used, and how many times they appear in the '
      'accounts.txt file.')
  parser.add_argument('-n', '--names', type=csv_paths, default=str(SCRIPT_DIR/'names.baseball.txt'),
    help='Use this file(s) as a source of names. Use these up before generating random ones. Give '
      'a comma-delimited list of paths. Default: %(default)s')
  parser.add_argument('-e', '--extra', type=csv_paths, default=str(SCRIPT_DIR/'names.mst3k.txt'),
    help='Add in some names from this file(s) at the end. Same format as --names. '
      'Default: %(default)s')
  parser.add_argument('-E', '--num-extra', default=5, type=int,
    help='Add this many names from the extra name files at the end. Default: %(default)s')
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

  used_name_counts = collections.Counter(get_used_names(args.accounts))
  logging.info(f'Info: {len(used_name_counts)} used names.')

  if args.print_used:
    print_used(used_name_counts)

  names_list = read_names_files(args.names)
  extra_names = read_names_files(args.extra)
  
  used_names_lc = set(lowercase_name_counts(used_name_counts))

  unused_static_names = get_unused_names(names_list, used_names_lc)

  needed_names = args.num_names - len(unused_static_names)

  unused_random_names = get_unused_random_names(needed_names, used_names_lc, gender='male')

  unused_names = unused_static_names + unused_random_names
  for name in sorted(unused_names[:args.num_names]):
    print(name)

  if args.extra:
    print('---')
    unused_extra_names = get_unused_names(extra_names, used_names_lc)
    for name in unused_extra_names[:args.num_extra]:
      print(name)


def read_names_files(names_paths):
  names = []
  for names_path in names_paths:
    names.extend(read_names_file(names_path))
  return names


def read_names_file(names_path):
  with names_path.open() as names_file:
    for line_raw in names_file:
      line = line_raw.strip()
      if not line.startswith('#'):
        yield line


def get_used_names(accounts_path):
  with accounts_path.open() as accounts_file:
    for entry in accountslib.parse(accounts_file):
      for account in entry.accounts.values():
        for section in account.values():
          for key, values in section.items():
            if key.lower() == 'name':
              for value in values:
                yield value.value


def lowercase_name_counts(name_counts):
  name_counts_lc = collections.Counter()
  for name, count in name_counts.items():
    name_counts_lc[name.lower()] += count
  return name_counts_lc


def print_used(names):
  print(f'{len(names)} used names:')
  for name, count in sorted(names.items(), key=lambda item: item[1], reverse=True):
    print(f'{count:4d} {name}')


def get_unused_names(names, used_names_lc):
  unused_names = []
  for name in randomize(names):
    if name.lower() not in used_names_lc:
      unused_names.append(name)
  return unused_names


def get_unused_random_names(num_names, used_names_lc, gender=None):
  unused_random_names = []
  while len(unused_random_names) < num_names:
    for name in get_random_names(num_names+1, gender):
      if name.lower() not in used_names_lc:
        unused_random_names.append(name)
        if len(unused_random_names) >= num_names:
          break
  return unused_random_names


def get_random_names(num_names, gender=None):
  for line_num, line in enumerate(run_rig(num_names, gender), 1):
    if line_num % 5 == 1:
      yield line


def run_rig(num_names, gender=None):
  if gender is None:
    gender_arg = []
  elif gender.startswith('m'):
    gender_arg = ['-m']
  elif gender.startswith('f'):
    gender_arg = ['-f']
  command = ('rig', *gender_arg, '-c', str(num_names))
  logging.info(f'Info: Running $ {" ".join(command)}')
  result = subprocess.run(command, encoding='utf8', stdout=subprocess.PIPE)
  return result.stdout.splitlines()


def csv_paths(csv_str):
  return [pathlib.Path(path_str) for path_str in csv_str.split(',')]


def randomize(list_):
  return sorted(list_, key=lambda e: random.random())


def fail(message):
  logging.critical('Error: '+str(message))
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception(message)


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
