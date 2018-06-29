#!/usr/bin/env python3
import argparse
import logging
import random
import sys
assert sys.version_info.major >= 3, 'Python 3 required'

ISSUERS = {
  'american': {
    'name': 'American Express',
    'length': 15,
    'IINs': [(34, 34), (37, 37)]
  },
  'mastercard': {
    'name': 'MasterCard',
    'length': 16,
    'IINs': [(2221, 2720), (51, 55)],
  },
  'visa': {
    'name': 'Visa',
    'length': 16,
    'IINs': [(4, 4)]
  },
  'discover': {
    'name': 'Discover Card',
    'length': 16,
    'IINs': [(6011, 6011), (64, 65)]
  }
}

ISSUER_NAMES = [issuer['name'] for issuer in ISSUERS.values()]

DESCRIPTION = """Generate a random credit card number that's valid according to the luhn algorithm.
Or, check whether a credit card number is valid. When generating a random card, by default, it will
randomly choose between the {} known issuers: {}.""".format(len(ISSUERS), ', '.join(ISSUER_NAMES))


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('cc', nargs='?',
    help='A credit card number to check for validity. If not given, will generate a random one.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  parser.add_argument('-r', '--random-iin', action='store_true',
    help="Don't pre-determine the issuer and generate the first few digits based on that. Instead, "
         'generate a purely random card number and edit the last digit to make it valid.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  if args.cc:
    cc = cc_from_str(args.cc)
    issuer = get_issuer(cc)
    if issuer is None:
      logging.error('Unrecognized issuer (not one of {}).'.format(', '.join(ISSUER_NAMES)))
    else:
      logging.warning('Issuer recognized: {}'.format(issuer))
    if is_valid_cc(cc):
      print('Valid')
    else:
      print('Invalid')
  else:
    if args.random_iin:
      issuer = None
    else:
      issuer = random.choice(tuple(ISSUERS.values()))
      logging.warning(issuer['name'])
    print(str_from_cc(make_random_cc(issuer)))


def str_from_cc(cc):
  return ''.join(map(str, cc))


def cc_from_str(cc_str):
  return [int(char) for char in cc_str]


def is_valid_cc(cc):
  """Return True if the Luhn checksum of the number is 0.
  The input must be a list of integers."""
  return get_luhn_checksum(cc) == 0


def get_luhn_checksum(cc):
  # The number is valid if this is 0.
  sum = 0
  parity = len(cc) % 2
  for i, digit in enumerate(cc):
    if i % 2 == parity:
      digit *= 2
      if digit > 9:
        digit -= 9
    sum += digit
  return sum % 10


def make_random_cc(issuer=None):
  if issuer is None:
    cc = get_rand_digits(16)
  else:
    iin = get_rand_iin(issuer)
    length = issuer['length'] - len(iin)
    cc = iin + get_rand_digits(length)
  return make_cc_valid(cc)


def get_rand_iin(issuer):
  iin_range = random.choice(issuer['IINs'])
  iin_int = random.randint(*iin_range)
  return [int(i) for i in str(iin_int)]


def get_rand_digits(num_digits):
  digits = []
  for i in range(num_digits):
    digits.append(random.randint(0, 9))
  return digits


def make_cc_valid(cc):
  while not is_valid_cc(cc):
    cc[-1] = (cc[-1]+1) % 10
  return cc


def get_issuer(cc):
  for issuer in ISSUERS.values():
    for iin_range in issuer['IINs']:
      iin_len = len(str(iin_range[0]))
      iin = cc[:iin_len]
      iin_int = int(''.join([str(i) for i in iin]))
      if iin_range[0] <= iin_int <= iin_range[1]:
        return issuer['name']
  return None


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
