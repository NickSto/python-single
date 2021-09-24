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
DEFAULTS = {'num_names':10, 'names':[], 'extra':[], 'num_extra':5, 'log':sys.stderr, 'volume':logging.WARNING}

def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  parser.add_argument('num_names', type=int, nargs='?',
    help='Choose and print this many names. Default: %(default)s')
  parser.add_argument('-a', '--accounts', metavar='accounts.txt', nargs='?', type=pathlib.Path,
    help='The accounts text file. Required, unless --args is given (and contains the file).')
  parser.add_argument('-A', '--args', metavar='args.txt', type=pathlib.Path,
    default=SCRIPT_DIR/'names.args.txt',
    help='Use arguments from this file, if it exists, instead of from the command line. Arguments '
      'can be separated by either a tab or newline character. Default: %(default)s')
  parser.add_argument('-u', '--print-used', action='store_true',
    help='Just print a list of all names already used, and how many times they appear in the '
      'accounts.txt file.')
  parser.add_argument('-r', '--rig', action='store_true',
    help="Just print names from rig. Don't use any other name sources.")
  parser.add_argument('-n', '--names', action='append', type=pathlib.Path,
    help='Use this file as a source of names. Use these up before generating random ones. Give '
      'a comma-delimited list of paths. Default: %(default)s')
  parser.add_argument('-e', '--extra', action='append', type=pathlib.Path,
    help='Add in some names from this file(s) at the end. Same format as --names. '
      'Default: %(default)s')
  parser.add_argument('-E', '--num-extra', type=int,
    help='Add this many names from the extra name files at the end. This is in addition to the '
      'number of primary names specified. Default: %(default)s')
  options.add_argument('-h', '--help', action='help',
    help='Print this argument help text and exit.')
  logs = parser.add_argument_group('Logging')
  logs.add_argument('-l', '--log', type=argparse.FileType('w'),
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = logs.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()

  # Initial arg parsing, just to get the --args argument and read in the args file.
  args = parser.parse_args(argv[1:])
  for arg, value in DEFAULTS.items():
    setattr(args, arg, value)
  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')
  if args.args.is_file():
    logging.info(f'Info: Using arguments from {args.args}.')
    args_list = read_args_file(args.args)
    args = parser.parse_args(args_list)

  # Read in the command line arguments and update the args from the args file.
  new_args = parser.parse_args(argv[1:])
  for arg in dir(args):
    if arg.startswith('_'):
      continue
    new_value = getattr(new_args, arg)
    if new_value is not None:
      if new_value == [pathlib.Path('')]:
        # Allow setting the --names or --extra to empty by giving an empty string.
        new_value = []
      setattr(args, arg, new_value)

  if args.accounts is None:
    logging.error(f'Error: Must give an accounts text file.')
    parser.print_usage()
    return 1

  # Read in the already-used names from the accounts file.

  used_name_counts = collections.Counter(get_used_names(args.accounts))
  logging.info(f'Info: {len(used_name_counts)} used names.')

  if args.print_used:
    print_used(used_name_counts)
    return 0

  used_names_lc = set(lowercase_name_counts(used_name_counts))

  # Print names from the --names file(s), if given.

  if args.rig:
    names_list = []
  else:
    names_list = read_names_files(args.names)
  unused_static_names = randomize(get_unused_names(names_list, used_names_lc))
  for name in sorted(unused_static_names[:args.num_names]):
    print(name)

  needed_names = args.num_names - len(unused_static_names)

  # Print random names (from rig), if needed.

  if needed_names:
    unused_random_names = get_unused_random_names(needed_names, used_names_lc, gender='male')
    if names_list:
      print('---')
    for name in sorted(unused_random_names[:needed_names]):
      print(name)

  # Print names from the --extra file(s), if given.

  if not args.rig and args.extra and args.num_extra > 0:
    extra_names = read_names_files(args.extra)
    print('---')
    unused_extra_names = randomize(get_unused_names(extra_names, used_names_lc))
    for name in unused_extra_names[:args.num_extra]:
      print(name)


def read_args_file(args_path):
  args = []
  with args_path.open() as args_file:
    for line_raw in args_file:
      line = line_raw.rstrip('\r\n')
      if line:
        args.extend(line.split('\t'))
  return args


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
  print(f'{len(names):4d} Used Names')
  print('===============')
  for name, count in sorted(names.items(), key=lambda item: item[1], reverse=True):
    print(f'{count:4d} {name}')


def get_unused_names(names, used_names_lc):
  """Subtract used names from the list `names`."""
  unused_names = []
  for name in names:
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
