#!/usr/bin/env python3
import argparse
import logging
import os
import re
import sys
import time
import requests
try:
  import youtube_dl
except ImportError:
  youtube_dl = None
assert sys.version_info.major >= 3, 'Python 3 required'

API_URL = 'https://www.googleapis.com/youtube/v3/'
DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('api_key')
  parser.add_argument('playlist_id',
    help='The playlist id.')
  parser.add_argument('-d', '--download',
    help='Download the videos to this directory too. This will also save metadata on each video '
         'to a text file, one per video.')
  parser.add_argument('-m', '--meta', action='store_true',
    help='Just save metadata file on each video.')
  parser.add_argument('-M', '--max-length', type=int, default=999999,
    help='Don\'t download videos longer than this. Give a time, in minutes. The metadata file '
         'will still be created, though.')
  parser.add_argument('--max-results', type=int, default=50,
    help='The maximum number of videos to fetch from the playlist at a time. It will always fetch '
         'all videos in the playlist, but this changes how big the chunks are.')
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

  if args.download:
    downloaded_videos = read_video_dir(args.download)

  playlist = fetch_playlist(args.api_key, args.playlist_id, args.max_results)

  for i, playlist_video in enumerate(playlist['items']):
    video_id = playlist_video['snippet']['resourceId']['videoId']
    video = fetch_video(args.api_key, video_id)
    if isinstance(video, str):
      channel = None
    else:
      channel = fetch_channel(args.api_key, video['snippet']['channelId'])
    print(format_metadata_human(i+1, video_id, video, channel))
    if args.download:
      #TODO: Allow skipping if the video was added to the playlist very recently.
      #      The video added date is in playlist['items'][i]['snippet']['publishedAt'].
      #TODO: Allow updating files to stay synced with playlist: delete videos removed from the
      #      playlist, rename files when index changes.
      if video_id in downloaded_videos:
        logging.warning('Video appears already downloaded. Skipping..')
      else:
        errors = []
        if args.meta:
          pass
        elif isinstance(video, str):
          logging.warning('Video missing. Skipping download..')
        elif parse_duration(video['contentDetails']['duration']) > args.max_length*60:
          logging.warning('Video too long to be downloaded. Skipping..')
        else:
          logging.warning('Downloading..')
          filename, errors = download_video(video_id, args.download, prefix='{} - '.format(i+1))
        save_metadata(args.download, i+1, video_id, video, channel, errors)
    print()


def read_video_dir(dirpath):
  videos = {}
  for filename in os.listdir(dirpath):
    fields = filename.split('.')
    if not (len(fields) >= 2 and fields[-2].endswith(']') and fields[-2][-16:-12] == '[id '):
      continue
    video_id = fields[-2][-12:-1]
    videos[video_id] = filename
  return videos


def format_metadata_human(index, video_id, video_data, channel_data):
  if isinstance(video_data, str):
    return '{}: [{}]\nhttps://www.youtube.com/watch?v={}'.format(index, video_data, video_id)
  else:
    return """{:<3s} {title}
Channel: {channel_title} - https://www.youtube.com/channel/{channel_id}
Upload date: {upload_date}
https://www.youtube.com/watch?v={video_id}""".format(
      str(index)+':',
      title=video_data['snippet']['title'],
      channel_title=channel_data['snippet']['title'],
      channel_id=channel_data['id'],
      upload_date=video_data['snippet']['publishedAt'][:10],
      video_id=video_id
    )


def format_metadata_yaml(video_id, video_data, channel_data, errors=()):
  if isinstance(video_data, str):
    return '{}: True\nurl: https://www.youtube.com/watch?v={}'.format(video_data, video_id)
  else:
    description = '\n  '.join(video_data['snippet']['description'].splitlines())
    yaml_str = """title: {title}
url: https://www.youtube.com/watch?v={video_id}
channel: {channel_title}
channelUrl: https://www.youtube.com/channel/{channel_id}
uploaded: {upload_date}
length: {length}
description: |
    {description}""".format(
      title=video_data['snippet']['title'],
      channel_title=channel_data['snippet']['title'],
      channel_id=channel_data['id'],
      upload_date=video_data['snippet']['publishedAt'][:10],
      video_id=video_id,
      length=parse_duration(video_data['contentDetails']['duration']),
      description=description
    )
    if 'blocked' in errors:
      yaml_str += '\nblocked: True'
    return yaml_str


def save_metadata(dest_dir, index, video_id, video_data, channel_data, errors=()):
  meta_path = os.path.join(dest_dir, '{}.metadata.yaml'.format(index))
  with open(meta_path, 'w') as meta_file:
    meta_file.write(format_metadata_yaml(video_id, video_data, channel_data, errors)+'\n')


def parse_duration(dur_str):
  assert dur_str.startswith('PT'), dur_str
  hours = 0
  minutes = 0
  seconds = 0
  for time_spec in re.findall(r'\d+[HMS]', dur_str):
    if time_spec.endswith('H'):
      hours = int(time_spec[:-1])
    elif time_spec.endswith('M'):
      minutes = int(time_spec[:-1])
    elif time_spec.endswith('S'):
      seconds = int(time_spec[:-1])
  return hours*60*60 + minutes*60 + seconds


##### Begin Youtube API section #####

def fetch_playlist(api_key, playlist_id, max_results=50):
  playlist = None
  params = {
    'playlistId':playlist_id,
    'maxResults':max_results,
    'part':'snippet',
    'key':api_key
  }
  nextPageToken = None
  done = False
  while not done:
    params['pageToken'] = nextPageToken
    data = call_api('playlistItems', params, api_key)
    nextPageToken = data.get('nextPageToken')
    if nextPageToken is None:
      done = True
    if playlist is None:
      playlist = data
    else:
      playlist['items'].extend(data['items'])
  return playlist


def fetch_channel(api_key, channel_id):
  params = {
    'id':channel_id,
    'part':'snippet',
  }
  data = call_api('channels', params, api_key)
  return data['items'][0]


def fetch_video(api_key, video_id):
  params = {
    'id':video_id,
    'part':'snippet,contentDetails'
  }
  data = call_api('videos', params, api_key)
  if data['items']:
    return data['items'][0]
  elif data['pageInfo']['totalResults'] == 1:
    return 'deleted'
  else:
    return 'private'


def call_api(api_name, params, api_key):
  our_params = params.copy()
  our_params['key'] = api_key
  response = requests.get(API_URL+api_name, params=our_params)
  if response.status_code != 200:
    error = get_error(response)
    if error:
      fail('Error fetching playlist data. Server message: '+str(error))
    else:
      fail('Error fetching playlist data. Received a {} response.'.format(response.status_code))
  return response.json()


def get_error(response):
  data = response.json()
  if 'error' in data:
    return data['error'].get('message')
  else:
    return None

##### End Youtube API section #####


##### Begin youtube-dl section #####

def download_video(video_id, destination, quality='18', prefix=''):
  filename_template = (prefix+'%(title)s [src %(uploader)s, %(uploader_id)s] '
                     '[posted %(upload_date)s] [id %(id)s].%(ext)s')
  prev_dir = os.getcwd()
  try:
    os.chdir(destination)
    ydl_opts = {
      'format':quality,
      'outtmpl':filename_template,
      'logger':YoutubeDlLogger(),
      #TODO: xattrs
    }
    try:
      call_youtube_dl(video_id, ydl_opts)
    except youtube_dl.utils.DownloadError as error:
      if hasattr(error, 'exc_info'):
        if error.exc_info[1].args[0] == 'requested format not available':
          del ydl_opts['format']
          call_youtube_dl(video_id, ydl_opts)
    filename = get_video_filename(DownloadMetadata, video_id)
    if filename is not None:
      set_date_modified(filename, DownloadMetadata['errors'])
    return filename, DownloadMetadata['errors']
  finally:
    os.chdir(prev_dir)


def call_youtube_dl(video_id, ydl_opts):
  DownloadMetadata['titles'] = []
  DownloadMetadata['merged'] = None
  DownloadMetadata['errors'] = []
  with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    ydl.download(['https://www.youtube.com/watch?v={}'.format(video_id)])


def get_video_filename(download_metadata, video_id):
  if download_metadata['merged']:
    logging.debug('Video created from merged video/audio.')
    filename = download_metadata['merged']
  elif len(download_metadata['titles']) == 1:
    filename = download_metadata['titles'][0]
  elif download_metadata['errors']:
    for error in download_metadata['errors']:
      if error == 'blocked':
        logging.error('Error: Video {} blocked.'.format(video_id))
    if not download_metadata['errors']:
      logging.error('Error: Video {} not downloaded.'.format(video_id))
    filename = None
  elif len(download_metadata['titles']) == 0:
    fail('Error: failed to determine filename of downloaded video {}'.format(video_id))
  elif len(download_metadata['titles']) > 1:
    fail('Error: found multiple potential filenames for downloaded video {}:\n{}'
         .format(video_id, '\n'.join(download_metadata['titles'])))
  return filename


def set_date_modified(path, errors):
  now = time.time()
  try:
    os.utime(path, (now, now))
  except FileNotFoundError:
    if not errors:
      fail('Error: Downloaded video {}, but downloaded file not found.'.format(path))


# Define global dict to workaround problem that some data is only available from log messages that
# can only be obtained by intercepting in a hook (no other way to return the data).
DownloadMetadata = {'titles':[], 'merged':None, 'errors':[]}

class YoutubeDlLogger(object):
  def debug(self, message):
    # Ignore standard messages.
    if message.startswith('[youtube]'):
      if (message.endswith(': Downloading webpage') or
          message.endswith(': Downloading video info webpage') or
          message.endswith(': Downloading MPD manifest')):
        return
    elif message.startswith('[dashsegments] Total fragments: '):
      return
    elif message.startswith('\r\x1b[K[download]'):
      if ' ETA ' in message[-20:]:
        return
    elif message.startswith('Deleting original file '):
      return
    # Extract video title info from log messages.
    if message.startswith('[download] Destination: '):
      DownloadMetadata['titles'].append(message[24:])
      return
    elif message.startswith('[ffmpeg] Merging formats into '):
      DownloadMetadata['merged'] = message[31:-1]
      return
    logging.info(message)
  def info(self, message):
    logging.info(message)
  def warning(self, message):
    logging.warning(message)
  def error(self, message):
    if message.startswith('\x1b[0;31mERROR:\x1b[0m This video contains content from '):
      if message.endswith('. It is not available.'):
        DownloadMetadata['errors'].append('blocked')
        return
    logging.error(message)
  def critical(self, message):
    logging.critical(message)

##### End youtube-dl section #####


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
