'''
Created on 12 Jan 2015

@author: Damian Shaw
'''

import os
import Queue
import time
import re

try:
    import httplib2
    from apiclient.discovery import build
    from apiclient.errors import HttpError
    from apiclient.http import BatchHttpRequest
    from oauth2client.client import flow_from_clientsecrets
    from oauth2client.file import Storage
    from oauth2client.tools import run_flow, argparser
except ImportError:
    print("Can't find google-api-python-client please install. \n"
          "Please use the provided requirements.txt. \n"
          "On Windows this would look something like: \n"
          "C:\Python27\Scripts>pip2.7.exe install -r requirements.txt")

from collections import namedtuple
from datetime import datetime, timedelta
from httplib import ResponseNotReady
from traceback import print_exception


__all__ = ('ytvideos')


class httpContextRequest(object):
    def __enter__(self):
        self.status = None
        return self

    def __exit__(self, etype, value, traceback):
        if etype is None:
            self.status = "Success"
            return True
        if issubclass(etype, HttpError):
            print("YouTube API returned HTTP %d : %s"
                  % (value.resp.status, value.content))
            time.sleep(15)
        elif issubclass(etype, ResponseNotReady):
            print("YouTube API returned HTTP ResponseNotReady: %s" % value)
            time.sleep(15)
        elif issubclass(etype, httplib2.ServerNotFoundError):
            print("YouTube API returned not available: %s" % value)
            time.sleep(60)
        elif issubclass(etype, Exception):
            print("Some unexpected exception with YouTube API:")
            print_exception(etype, value, traceback)
            print("Sleeping for 5 mins")
            time.sleep(300)
        else:
            return False
        return True


class ytvideos(object):
    '''Class to get information about YouTube videos from specificied
    channels playlists'''

    def __init__(self, settings=None):
        '''Set some stuff up, including initially login to youtube to
        get required channel data. This tests if the credentials
        provided are correct and throws an exception if they are not'''
        self.set = settings

        # This dictionary is a record of the new YouTube videos
        # It will map a YouTube video ID to a named tuple containing
        # the title of the video and date it was added to the upload
        # playlist
        self.records = {}
        self.record = namedtuple('record', ['title', 'date'])

        # FIFO queue used by callbacks to temporary store video info
        # before upload, youtubeId needs to be held alongside
        self.q = Queue.Queue()

        # Login to YouTube using the Google provided API
        self.youtube = self.initilize_youtube(settings)
        print('Successfully authenticated against YouTube')

        # This dictionary maps the channel id to the upload
        # playlist id, this dictionary is populated with the 2 methods
        # getUserAccountNameDetails and getSubscriptionUploadPlayLists
        self.channel_videos = {}
        self.channel_titles = {}
        self.getUserAccountNameDetails()
        self.getUserAccountIdDetails()
        if self.set.subscriptions:
            self.getSubscriptionUploadPlayLists()
        print('Successfully got channel information from YouTube')

    def initilize_youtube(self, settings):
        args = argparser.parse_args()
        args.noauth_local_webserver = True

        client_secrets_file = "client_secrets.json"
        missing_secrets_message = """
        WARNING: Please configure OAuth 2.0

        By installing a client_secrets.json here:
        %s

        You can get this file by:

        1. Go to https://console.developers.google.com/project
        2. Create a project if not already
        3. In project go to: APIs & auth > Credentials
        4. Click "Create new Client ID"
        5. Choose installed application > Other
        6. Click "Download JSON"
        7. Copy file to the path mentioned above
        """ % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           client_secrets_file))

        # This OAuth 2.0 access scope allows for read-only access to the
        # authenticated user's account, but not other types of account access.
        yt_scope = "https://www.googleapis.com/auth/youtube.readonly"
        yt_api_service_name = "youtube"
        yt_api_version = "v3"

        flow = flow_from_clientsecrets(client_secrets_file,
                                       message=missing_secrets_message,
                                       scope=yt_scope)

        storage = Storage("temp-oauth2.json")
        credentials = storage.get()

        if credentials is None or credentials.invalid:
            credentials = run_flow(flow, storage, args)

        for _ in xrange(500):
            with httpContextRequest() as request:
                youtube = build(yt_api_service_name, yt_api_version,
                                http=credentials.authorize(httplib2.Http()))

            if request.status == 'Success':
                break

        return youtube

    def delKeys(self, keys):
        counter = 0
        for key in keys:
            try:
                del self.records[key]
            except KeyError:
                pass
            else:
                counter += 1
        return counter

    def getVideoDescription(self, videoId):
        for _ in xrange(500):
            with httpContextRequest() as request:
                video_response = self.youtube.videos().list(
                    id=videoId, part='snippet'
                    ).execute()

            if request.status == 'Success':
                break

        return video_response["items"][0]["snippet"]["description"]

    def getUserAccountNameDetails(self):
        '''Get user playlists defined in the settings file'''
        for account in self.set.accounts:
            for _ in xrange(500):
                with httpContextRequest() as request:
                        channels_response = self.youtube.channels().list(
                            forUsername=account, part='snippet'
                            ).execute()

                if request.status == 'Success':
                    break

            try:
                for item in channels_response['items']:
                    channel_id = item["id"]
                    title = item["snippet"]["title"]
                    self.channel_titles[channel_id] = title
                    self.channel_videos[channel_id] = []
            except KeyError:
                print("There were no channels in the youtube account %s"
                      % account)

    def getUserAccountIdDetails(self):
        '''Get user playlists defined in the settings file'''
        for account in self.set.account_ids:
            for _ in xrange(500):
                with httpContextRequest() as request:
                    channels_response = self.youtube.channels().list(
                        id=account, part='snippet'
                        ).execute()

                if request.status == 'Success':
                    break

            try:
                for item in channels_response['items']:
                    channel_id = item["id"]
                    title = item["snippet"]["title"]
                    print("Got information for account: %s" % title)
                    self.channel_titles[channel_id] = title
                    self.channel_videos[channel_id] = []
            except KeyError:
                print("There were no channels in the youtube account %s"
                      % self.channel_titles[account])

    def getSubscriptionUploadPlayLists(self):
        # Get playlists from the users subscribed channels
        nextPageToken = None
        while True:
            channel_ids = []
            # Grab 1 page of results from YouTube
            for _ in xrange(500):
                with httpContextRequest() as request:
                    subscriber_items = self.youtube.subscriptions().list(
                        mine=True, part="snippet", maxResults=50,
                        pageToken=nextPageToken
                        ).execute()

                if request.status == 'Success':
                    break

            for item in subscriber_items["items"]:
                channel_ids.append(item["snippet"]["resourceId"]["channelId"])

            # API only accepts at most 50 item IDs
            channels_by_comma = ",".join(channel_ids)
            for _ in xrange(500):
                with httpContextRequest() as request:
                    channels_response = self.youtube.channels().list(
                        id=channels_by_comma, part='snippet'
                        ).execute()

                if request.status == 'Success':
                    break

            try:
                for item in channels_response['items']:
                    channel_id = item["id"]
                    title = item["snippet"]["title"]
                    self.channel_titles[channel_id] = title
                    self.channel_videos[channel_id] = []
                    print("From subscriptions adding channel: %s" % title)
            except KeyError:
                # This Channel was already defined by the user
                pass

            try:
                nextPageToken = subscriber_items["nextPageToken"]
            except KeyError:
                # Reached end of list
                break

    def getChannelNewestVideosCallback(self, request_id, response, exception):
        if exception is not None:
            print(exception)
        else:
            # Loop through results and add new videos to queue
            number_of_new_videos = 0
            for item in response['items']:
                snippet = item["snippet"]
                cid = snippet["channelId"]
                YTid = item["id"]["videoId"]
                title = snippet["title"]
                description = snippet["description"]
                date = snippet["publishedAt"]
                date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.000Z")

                # Check if video has already been processed
                if YTid in self.channel_videos[cid]:
                    continue

                # Check if required substring in video title,
                # checking against case-insensitive alpha-numeric
                # parts of string only
                title_contain = self.set.title_must_contain
                if title_contain:
                    title_contain = re.sub('[\W_]+', '', title_contain).lower()
                    check_title = re.sub('[\W_]+', '', title).lower()
                    if title_contain not in check_title:
                        continue

                # Check if required substring in video title,
                # checking against case-insensitive alpha-numeric
                # parts of string only
                desc_contain = self.set.description_must_contain
                if desc_contain:
                    desc_contain = re.sub('[\W_]+', '', desc_contain).lower()
                    check_desc = re.sub('[\W_]+', '', description).lower()
                    if desc_contain not in check_desc:
                        # The description field is truncated, we need to do a
                        # lookup on that video details to confirm it's really
                        # Not in the description
                        ful_desc = self.getVideoDescription(YTid)
                        check_ful_desc = re.sub('[\W_]+', '', ful_desc).lower()
                        if desc_contain not in check_ful_desc:
                            continue

                number_of_new_videos += 1
                self.q.put([YTid, self.record(title=title, date=date)])
                self.channel_videos[cid].append(YTid)

            if number_of_new_videos:
                print("Got %d new videos from channel: %s" %
                      (number_of_new_videos, self.channel_titles[cid]))

    def getNewestVideos(self):
        # Temporary fix to overcome oauth expiries, should only call once oauth
        # is expired (to be fixed)
        self.youtube = self.initilize_youtube(self.set)
        self.records = {}

        # When subscription count is large it's important to batch all the
        # HTTP requests together as 1 http request. This will break if
        # Channel list is > 1000 (to be fixed)
        batch = BatchHttpRequest(callback=self.getChannelNewestVideosCallback)

        # Add each playlist to the batch request
        for channel_id in self.channel_titles:

            # We should be getting videos directly off the playlist items
            # But YouTube API takes 15 - 60 mins to update this list
            # So instead search.list is used at great quota cost
            # Also since moving to batch we only get the last 50 results from
            # a channel, TO DO: collate nextPageTokens if require more than 50
            check_after = (datetime.utcnow() -
                           timedelta(days=self.set.days_uploaded_after))
            check_after = check_after.isoformat("T") + "Z"
            batch.add(
                self.youtube.search().list(
                    part='snippet', maxResults=50, channelId=channel_id,
                    type='video', safeSearch='none', publishedAfter=check_after
                    )
                )

        for _ in xrange(500):
            with httpContextRequest() as request:
                batch.execute()

            if request.status == 'Success':
                break

        counter = 0
        while not self.q.empty():
            try:
                [YTid, record] = self.q.get()
                self.records[YTid] = record
                counter += 1
            except:
                break

        return counter
