#!/usr/bin/env python3
import argparse
import glob
import logging
import os
import sys
import youtube
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  subparsers = parser.add_subparsers(dest='command')
  mark = subparsers.add_parser('mark',
    help='Mark in the metadata files which videos have been successfully downloaded. Note: If a '
         'file already says it\'s downloaded but the video is now missing, this will not remove '
         'the downloaded mark!')
  mark.add_argument('dir',
    help='Videos directory.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
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

  if args.command == 'mark':
    import yaml
    for filename in sorted(os.listdir(args.dir)):
      if not filename.endswith('.metadata.yaml'):
        logging.debug('File doesn\'t look like a metadata file: '+filename[:40])
        continue
      fields = filename.split('.')
      if len(fields) != 4 or len(fields[1]) != 11:
        logging.warning('Malformed metadata filename: '+filename)
        continue
      try:
        index = int(fields[0])
      except ValueError:
        logging.warning('Malformed metadata filename index: '+filename)
        continue
      meta_path = os.path.join(args.dir, filename)
      with open(meta_path) as yaml_file:
        metadata = yaml.safe_load(yaml_file)
      if metadata.get('downloaded'):
        logging.info('Video already marked as downloaded: '+filename)
        continue
      if len(metadata.get('url', '')) != 43:
        logging.warning('Malformed url in metadata file {}: {!r}'.format(filename, metadata.get('url')))
        continue
      video_id = metadata['url'][-11:]
      match = False
      for video_path in glob.glob('{}/{} - *'.format(args.dir, index)):
        candidate_id = youtube.parse_video_id(os.path.basename(video_path), strict=True)
        if candidate_id == video_id:
          match = True
          break
      if not match or os.path.getsize(video_path) == 0:
        logging.info('No non-empty video file found for '+filename)
        continue
      print('Marking {}'.format(filename))
      with open(meta_path, 'a') as meta_file:
        meta_file.write('downloaded: true')


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
