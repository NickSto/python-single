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

# https://twitter.com/lrgmnn/status/813635533658144768
BASE_MEN = (
  ('Sleve', 'McDichael'), ('Onson', 'Sweemey'), ('Darryl', 'Archideld'), ('Anatoli', 'Smorin'),
  ('Rey', 'McSriff'), ('Glenallen', 'Mixon'), ('Mario', 'Mcrlwain'), ('Raul', 'Chamgerlain'),
  ('Kevin', 'Nogilny'), ('Tony', 'Smehrik'), ('Bobson', 'Dugnutt'), ('Willie', 'Dustice'),
  ('Jeromy', 'Gride'), ('Scott', 'Dourque'), ('Shown', 'Furcotte'), ('Dean', 'Wesrey'),
  ('Mike', 'Truk'), ('Dwigt', 'Rortugal'), ('Tim', 'Sandaele'), ('Karl', 'Dandleton'),
  ('Mike', 'Sernandez'), ('Todd', 'Bonzalez')
)
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

  used_names = collections.Counter(get_names(args.accounts))
  logging.info(f'Info: {len(used_names)} used names.')

  if args.print_used:
    print_used(used_names)
  
  used_names_lc = lowercase_name_counts(used_names)

  unused_base_men = get_unused_base_men(BASE_MEN, used_names_lc)

  needed_names = args.num_names - len(unused_base_men)

  unused_random_names = get_unused_random_names(needed_names, used_names_lc, gender='male')

  unused_names = unused_base_men + unused_random_names
  for name in sorted(unused_names[:args.num_names]):
    print(name)


def get_names(accounts_path):
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


def get_unused_base_men(base_men, used_names_lc):
  unused_base_men = []
  for first, last in sorted(base_men, key=lambda e: random.random()):
    name = f'{first} {last}'
    if name.lower() not in used_names_lc:
      unused_base_men.append(name)
  return unused_base_men


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
