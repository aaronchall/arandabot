'''
Created on 12 Jan 2015

@author: Damian Shaw
description: |
    This module contains the main arandabot function that 
    queries Youtube and then posts to reddit.
'''
from __future__ import division, print_function

# Python standard modules
import time
from datetime import datetime, timedelta

# My modules
import ytvideos
import redditsubmissions

__all__ = ['arandabot']


def arandabot(settings):
    '''Arandabot is the main running of the bot'''

    # Get settings
    script_settings = settings.script
    yt_settings = settings.youtube
    reddit_settings = settings.reddit
    seconds_to_sleep = script_settings.seconds_to_sleep

    # Login to YouTube and get channel information
    yt = ytvideos.ytvideos(settings=yt_settings)

    # 0.95 and 0.5 are magic numbers based on anecdotal observations
    # of how slow the YouTube API is.
    if script_settings.loop_forever:
        estimated_quota_cost = (0.95*len(yt.channel_titles)*86400
                                   // (seconds_to_sleep + 0.5))*102
    else:
        estimated_quota_cost = int(0.95*len(yt.channel_titles)*1440)*102

    print("50,000,000 is your maximum YouTube API daily quota limit\n"
          "{0:,} is your estimated maximum cost".format(estimated_quota_cost))

    # Login in to reddit
    r = redditsubmissions.redditsubmissions(settings=reddit_settings)

    # script logic
    loop_number = script_settings.number_of_loops
    while script_settings.loop_forever or loop_number > 0:
        loop_number -= 1

        number_yt_videos = yt.getNewestVideos()
        if number_yt_videos or script_settings.heartbeat:
            print("{0} new YouTube videos found".format(number_yt_videos))

        if yt.records:
            if script_settings.repost_protection:
                r.getYouTubeURLs()
                duplicate_count = yt.delKeys(r.records)
                print("{0} videos already posted on Reddit".format(duplicate_count))

            for YTid in sorted(yt.records, key=lambda k: yt.records[k].date):
                r.submitContent(
                    title=yt.records[YTid].title.encode('ascii', 'ignore'),
                    link='https://www.youtube.com/watch?v=' + YTid
                )

        time.sleep(seconds_to_sleep)
