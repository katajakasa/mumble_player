# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import pymumble
import audioread
import time
import audioop
import os
from progressbar import ProgressBar, Bar, Percentage, Timer
import datetime


class Playlist(object):
    def __init__(self):
        self.files = []

    def load_from_file(self, playlist):
        rel_base_path = os.path.dirname(os.path.abspath(playlist))
        with open(playlist, 'rb') as f:
            for row in f:
                # Ignore comment rows
                if row.startswith('#'):
                    continue

                row = row.rstrip('\r\n')
                if os.path.isabs(row):
                    self.files.append(row)
                else:
                    self.files.append(os.path.join(rel_base_path, row))

    def add_file(self, filename):
        self.files.append(filename)


class MumblePlayer(object):
    def __init__(self, host, port, user, password=None, key_file=None, cert_file=None):
        self.host = host
        self.port = port
        self.mumble = pymumble.Mumble(host, port=port,
                                      user=user, password=password,
                                      keyfile=key_file, certfile=cert_file)

    def connect(self):
        self.mumble.start()
        self.mumble.is_ready()
        self.mumble.users.myself.comment("Mumble player v0.1")
        self.mumble.users.myself.unmute()
        self.mumble.set_bandwidth(200000)

    def join_channel(self, channel):
        self.mumble.channels.find_by_name(channel).move_in()

    def play(self, playlist, volume=None):
        song_number = 0
        total_songs = len(playlist.files)
        for filename in playlist.files:
            # Disregard nonexistent files.
            if not os.path.exists(filename):
                print("File '{}' does not exist, skipping.".format(filename))
                continue

            # Open audio file with audioread module. This may crash if proper decoders are not installed!
            with audioread.audio_open(filename) as f:
                # TODO: Only show one progress bar, not a new one for every song ?
                widgets = [
                    '[{}/{}] {}'.format(song_number, total_songs, os.path.basename(filename)),
                    ' ', Bar(left='[', right=']'),
                    ' ', Percentage(),
                    ' ', Timer(),
                    ' of ', str(datetime.timedelta(seconds=f.duration)).split('.', 2)[0]
                ]
                with ProgressBar(max_value=f.duration, widgets=widgets) as progress:
                    bytes_position = 0
                    last_updated = 0
                    bps = 2 * f.channels * f.samplerate
                    ratecv_state = None
                    for buf in f:
                        # Update progressbar when necessary
                        bytes_position += len(buf)
                        sec_position = bytes_position / bps
                        if int(sec_position) > last_updated:
                            progress.update(sec_position)
                            last_updated = int(sec_position)

                        # Wait if there is no need to fill the buffer
                        while self.mumble.sound_output.get_buffer_size() > 1.0:
                            time.sleep(0.01)

                        # Convert audio if necessary. We want precisely 16bit 48000Hz mono audio for mumble.
                        if f.channels != 1:
                            buf = audioop.tomono(buf, 2, 0.5, 0.5)
                        if f.samplerate != 48000:
                            buf, ratecv_state = audioop.ratecv(buf, 2, 1, f.samplerate, 48000, ratecv_state)
                        if volume:
                            buf = audioop.mul(buf, 2, volume)

                        # Insert to mumble buffer
                        self.mumble.sound_output.add_sound(buf)
            song_number += 1


def main():
    parser = argparse.ArgumentParser(description='Mumble audio player')
    parser.add_argument('-f', '--file',
                        type=str,
                        dest='filename',
                        metavar="FILE",
                        help='Audio file',
                        required=True)
    parser.add_argument('-k', '--keyfile',
                        type=str,
                        dest='keyfile',
                        metavar="FILE",
                        help='SSL Private key file',
                        default=None)
    parser.add_argument('-e', '--certfile',
                        type=str,
                        dest='certfile',
                        metavar="FILE",
                        help='SSL Public key file',
                        default=None)
    parser.add_argument('-a', '--address',
                        type=str,
                        dest='address',
                        help='Address',
                        default='localhost')
    parser.add_argument('-P', '--port',
                        type=int,
                        dest='port',
                        help='Port',
                        default=64738)
    parser.add_argument('-u', '--username',
                        type=str,
                        dest='username',
                        help='Username',
                        default='mumbleplayer')
    parser.add_argument('-p', '--password',
                        type=str,
                        dest='password',
                        help='Password',
                        default=None)
    parser.add_argument('-c', '--channel',
                        type=str,
                        dest='channel',
                        required=True)
    parser.add_argument('-v', '--volume',
                        type=float,
                        dest='volume',
                        default=1.0)
    args = parser.parse_args()

    # Set correct volume
    if args.volume < 0.01:
        args.volume = 0.01
    if args.volume > 2.0:
        args.volume = 2.0

    # Make sure public certificate file and key file are both either set or not set (not either or)
    if bool(args.certfile) != bool(args.keyfile):
        print("Both cert and keyfiles must be either set or not set, not either-or!")
        exit(1)

    # Check file existence
    if args.certfile and not os.path.exists(args.certfile):
        print("Public certificate file {} does not exist!".format(args.certfile))
        exit(1)
    if args.keyfile and not os.path.exists(args.keyfile):
        print("Private key file {} does not exist!".format(args.keyfile))
        exit(1)
    if not os.path.exists(args.filename):
        print("Audio file {} does not exist!".format(args.filename))
        exit(1)

    # Print out some info
    print("Connecting to '{}:{}' as '{}'".format(args.address, args.port, args.username))
    print("Joining channel '{}'".format(args.channel))
    print("Playback volume set as '{}'".format(args.volume))
    if args.certfile and args.keyfile:
        print("Using certificates:")
        print(" * Public key = {}".format(args.certfile))
        print(" * Private key = {}".format(args.keyfile))

    # Create a playlist
    playlist = Playlist()
    if os.path.splitext(args.filename)[1] == '.m3u':
        playlist.load_from_file(args.filename)
        print("Playlist loaded with {} items.".format(len(playlist.files)))
    else:
        playlist.add_file(args.filename)

    # Start up the player
    player = MumblePlayer(args.address, args.port,
                          user=args.username, password=args.password,
                          key_file=args.keyfile, cert_file=args.certfile)
    player.connect()
    player.join_channel(args.channel)
    try:
        player.play(playlist, volume=args.volume)
    except KeyboardInterrupt:
        print("Playback interrupted")


if __name__ == '__main__':
    main()
