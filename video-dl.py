#!/usr/bin/env python3
import argparse
import distutils.spawn
import logging
import os
import re
import subprocess
import sys
import urllib.parse
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Download and label a video using youtube-dl."""
YOUTUBE_DL_ARGS = ['--no-mtime', '--add-metadata', '--xattrs']
SUPPORTED_SITES = {
  'youtube': {
    'domain':'youtube.com',
    'qualities': {
      '360':'18',
      '640':'18',
      '480':'135+250',  # 80k audio, 480p video
      '720':'22',
      '1280':'22',
    }
  },
  'vimeo': {
    'domain':'vimeo.com'
  },
  'facebook': {
    'domain':'facebook.com',
    'qualities': {
      '360':'dash_sd_src',
      '640':'dash_sd_src',
      '18':'dash_sd_src',
      '720':'dash_hd_src',
      '1280':'dash_hd_src',
      '22':'dash_hd_src',
    }
  },
  'instagram': {
    'domain':'instagram.com'
  },
  'twitter': {
    'domain':'twitter.com'
  },
  'dailymotion': {
    'domain':'dailymotion.com'
  },
  'twitch': {
    'domain':'clips.twitch.tv'
  }
}
QUALITY_SITES = [name for name, site in SUPPORTED_SITES.items() if 'qualities' in site]


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('url',
    help='Video url.')
  parser.add_argument('title', nargs='?',
    help='Video title for filename.')
  parser.add_argument('-F', '--formats', action='store_true',
    help='Just print the available video quality options.')
  parser.add_argument('-f', '--quality',
    help='Video quality to request. Only works for {}.'.format([', '.join(QUALITY_SITES)]))
  parser.add_argument('-n', '--get-filename', action='store_true')
  #TODO: parser.add_argument('-c', '--convert-to')
  #TODO: parser.add_argument('-p', '--posted')
  #      Or just interactively ask for the date.
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

  if not distutils.spawn.find_executable('youtube-dl'):
    fail("Error: 'youtube-dl' command not found.")

  if args.formats:
    subprocess.run(('youtube-dl', '-F', args.url))
    return

  site = site_is_supported(args.url)
  if not site:
    fail(
      'Error: URL {!r} is not from a supported site ({}).'
      .format(args.url, ', '.join([site['domain'] for site in SUPPORTED_SITES.values()]))
    )

  qual_key = None
  if args.quality:
    qualities = site.get('qualities')
    if not qualities:
      fail('Error: --quality only works with '+[', '.join(QUALITY_SITES)])
    qual_key = qualities.get(args.quality, args.quality)

  formatter = Formatter(site, args.url, args.title)
  fmt_str = formatter.get_format_string()

  end_args = ['-o', fmt_str, args.url]
  if args.quality:
    end_args = ['-f', qual_key] + end_args

  if args.get_filename:
    cmd = ['youtube-dl', '--get-filename'] + end_args
  else:
    cmd = ['youtube-dl'] + YOUTUBE_DL_ARGS + end_args
    # Kludge to work around bug in dailymotion downloader.
    if site['name'] == 'dailymotion':
      cmd.remove('--add-metadata')
    print(format_command(cmd))
  subprocess.run(cmd)


def site_is_supported(url):
  domain = urllib.parse.urlparse(url).netloc
  for name, site in SUPPORTED_SITES.items():
    supported_domain = site['domain']
    if domain.endswith(supported_domain):
      site['name'] = name
      return site
  return False


def format_command(cmd):
  escaped_args = cmd
  for i, arg in enumerate(cmd):
    escaped_args[i] = arg
    for char in ' ?&;\'":$':
      if char in arg:
        escaped_args[i] = repr(arg)
        break
  return '$ '+' '.join(escaped_args)


class Formatter:

  def __init__(self, site, url, title=None):
    self.site = site
    self.url = url
    if title is None:
      self.title = '%(title)s'
    else:
      self.title = title

  def get_format_string(self):
    metaformatter = getattr(self, 'format_{name}'.format(**self.site))
    return self.title+' '+metaformatter()

  def format_youtube(self):
    uploader_id = get_format_value(self.url, 'uploader_id')
    # Only use both uploader and uploader_id if the id is a channel id like "UCZ5C1HBPMEcCA1YGQmqj6Iw"
    if re.search(r'^UC[a-zA-Z0-9_-]{22}$', uploader_id):
      logging.warning(
        f'uploader_id {uploader_id} looks like a username, not a channel id. Omitting channel id..'
      )
      return '[src %(uploader_id)s] [posted %(upload_date)s] [id %(id)s].%(ext)s'
    else:
      return '[src %(uploader)s, %(uploader_id)s] [posted %(upload_date)s] [id %(id)s].%(ext)s'

  def format_vimeo(self):
    return '[src vimeo.com%%2F%(uploader_id)s] [posted %(upload_date)s] [id %(id)s].%(ext)s'

  def format_twitch(self):
    match = re.search(r'^https?://clips.twitch.tv/([^/?]+)((\?|/).*)?$', self.url)
    assert match, self.url
    video_id = match.group(1)
    return f'[src twitch.tv%%2F%(creator)s] [posted %(upload_date)s] [id {video_id}].%(ext)s'

  def format_facebook(self):
    FACEBOOK_REGEX = r'facebook\.com/[^/?]+/videos/[0-9]+'
    url = self.url
    good_url = False
    match = re.search(FACEBOOK_REGEX, url)
    if match:
      good_url = True
    else:
      cmd = ('curl', '-s', '--write-out', '%{redirect_url}', '-o', os.devnull, url)
      result = subprocess.run(cmd, stdout=subprocess.PIPE)
      new_url = str(result.stdout, 'utf8')
      match = re.search(FACEBOOK_REGEX, new_url)
      if match:
        url = new_url
        good_url = True
    escaped_url = self.simplify_url(url)
    return f'[posted %(upload_date)s] [src {escaped_url}].%(ext)s'

  def format_instagram(self):
    return self._format_instatwit()

  def format_twitter(self):
    return self._format_instatwit()

  def _format_instatwit(self):
    upload_date = get_format_value(self.url)
    if upload_date == 'NA':
      logging.warning(
        'No upload date could be obtained! You might want to put it in yourself:\n'
        '[posted YYYYMMDD]'
      )
      posted_fmt=''
    else:
      posted_fmt='[posted %(upload_date)s] '
    domain = self.site['domain']
    return posted_fmt+f'[src {domain}%%2F%(uploader_id)s] [id %(id)s].%(ext)s'

  def format_dailymotion(self):
    simple_url = self.simplify_url(self.url)
    return f'[posted %(upload_date)s] [src {simple_url}].%(ext)s'

  def simplify_url(self, url):
    parts = urllib.parse.urlparse(url)
    assert parts.netloc.endswith(self.site['domain']), url
    simple_url = self.site['domain']+parts.path
    return double_escape_url(simple_url)


def get_format_value(url, key):
  cmd = ('youtube-dl', '--get-filename', '-o', f'%({key})s', url)
  result = subprocess.run(cmd, stdout=subprocess.PIPE)
  return str(result.stdout, 'utf8')


def double_escape_url(url):
  """Percent-encode a URL, then escape the %'s so they're safe for youtube-dl format strings."""
  return urllib.parse.quote(url, safe='').replace('%', '%%')


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
