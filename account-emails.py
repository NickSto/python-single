#!/usr/bin/env python3
import os
import sys
import argparse
import collections
import accountslib
try:
  from utillib import console
except ImportError:
  console = None

DEFAULT_TERMWIDTH = 80
USAGE = "%(prog)s [options]"
DESCRIPTION = """Go through my accounts and find all the dot-variations of my spam email addresses
I've used."""


def main(argv):

  parser = argparse.ArgumentParser(description=DESCRIPTION)

  parser.add_argument('accounts_path', metavar='accounts.txt', nargs='?', type=os.path.expanduser,
    default='~/annex/Info/reference, notes/accounts.txt',
    help='The accounts text file. Default: %(default)s.')
  parser.add_argument('-e', '--email', default='nmapsy',
    help='The email address to look for. Default: %(default)s')
  parser.add_argument('-R', '--no-relay', dest='relay', default=True, action='store_false',
    help="Don't include Firefox Relay addresses.")
  parser.add_argument('-c', '--choose', action='store_true',
    help='Just choose an unused email, or if all are used, the least-often used one.')
  parser.add_argument('-t', '--tabs', action='store_true',
    help='Print tab-delimited lines with no colons (computer-readable).')
  parser.add_argument('-D', '--no-collapse-dots', dest='collapse_dots', action='store_false',
    default=True,
    help='Print addresses that differ by number of consecutive dots as distinct addresses.')
  parser.add_argument('--max-output', type=int, default=256,
    help='If the number of dot combinations is greater than this, fail instead of flooding the '
      'terminal. Default: %(default)s')

  args = parser.parse_args(argv[1:])

  if console is None:
    termwidth = DEFAULT_TERMWIDTH
  else:
    termwidth = console.termwidth()
  entries = collections.defaultdict(list)

  # Create all possible combinations of dots in the username.
  # (Only considers single dots between letters, not multiple.)
  basenames = collections.defaultdict(lambda: 0)
  # How many places are there for dots in-between characters in the email?
  places = len(args.email)-1
  if 2**places > args.max_output:
    fail('Error: Length of email {!r} would give more than --max-output combinations ({} > {})'
         .format(args.email, 2**places, args.max_output))
  # Make a format string like '{:05b}' that will print a binary sequence of 1's and 0's as wide as
  # the number of places.
  format_str = '{:0'+str(places)+'b}'
  # The number of possible dot combinations is 2**places.
  for i in range(2**places):
    email = ''
    # Get a string of 0's and 1's representing presence or absence of dots.
    pattern = format_str.format(i)
    # Build an email string with dots where there are 0's in the pattern string.
    for char, bit in zip(args.email, pattern):
      if bit == '0':
        email += char
      elif bit == '1':
        email += char + '.'
    email += args.email[-1]
    basenames[email] = 0

  # Read accounts.txt file.
  relays = collections.defaultdict(list)
  with open(args.accounts_path, 'rU') as accounts_file:
    for entry in accountslib.parse(accounts_file):
      for account in entry.accounts.values():
        for section in account.values():
          for key, values in section.items():
            if key.lower() == 'email':
              for value in values:
                username, *rest = value.value.split('@')
                if len(rest) == 1:
                  domain = rest[0]
                elif len(rest) == 0:
                  domain = None
                elif len(rest) > 1:
                  raise ValueError(f'Invalid email {value.value!r}')
                basename = username.split('+')[0]
                if basename.replace('.', '') == args.email:
                  if args.collapse_dots:
                    basename = collapse_dots(basename)
                  basenames[basename] += 1
                  entries[basename].append(entry.name)
                elif args.relay and domain == 'relay.firefox.com':
                  relays[value.value].append(entry.name)

  # Print all the used combinations.
  least_used = None
  uses_min = 999999999
  dots_min = len(args.email)
  basename_list = reversed(sorted(basenames.keys(), key=lambda basename: basenames[basename]))
  for basename in basename_list:
    if args.choose:
      # Track the email with the fewest uses, and if there are multiple with the fewest, find the
      # one out of those with the fewest dots.
      uses = basenames[basename]
      dots = len(basename) - len(args.email)
      if uses < uses_min:
        least_used = basename
        uses_min = uses
        dots_min = dots
      elif uses == uses_min:
        if dots < dots_min:
          least_used = basename
          dots_min = dots
    else:
      # If not --choose, just print every email.
      print_email(basename, basenames[basename], entries[basename], args.tabs, termwidth)
  if args.choose:
    print_email(least_used, uses_min, entries[least_used], args.tabs, termwidth)
  else:
    for relay, entries in relays.items():
      username, domain = relay.split('@')
      domain_abbrev = domain.split('.')[0]
      print_email(f'{username}@{domain_abbrev}', len(entries), entries, args.tabs, termwidth)


def collapse_dots(dotted_str):
  collapsed_str = dotted_str
  last_str = None
  while collapsed_str != last_str:
    last_str = collapsed_str
    collapsed_str = collapsed_str.replace('..', '.')
  return collapsed_str


def print_email(email, uses, entries, tabs=False, width=80):
  if tabs:
    print(email, uses, ','.join(entries), sep='\t')
  else:
    entries_str = ', '.join(entries)[:width-24]
    print(f'{email+":":17s}{uses:<4d}{entries_str}')


def fail(message):
  sys.stderr.write(message+"\n")
  sys.exit(1)

if __name__ == '__main__':
  sys.exit(main(sys.argv))
