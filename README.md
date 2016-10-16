# mumble_player

A very simple cli for playing audio files and playlist on Mumble channel

# Installation

1. Install Python 2.7 and if on windows, make sure the binaries end up in PATH.
2. Get [PyMumble](https://github.com/azlux/pymumble) from  and install it manually
3. Run `pip install -r requirements.txt` in project directory
4. Run client. See help with `python mumbleplayer.py -h`

# Notes

Filename can be either an m3u playlist or a normal audiofile. If playlist,
all files will be played one by one.

Note that mumbleplayer uses celt library, and requires libcelt installed.
On windows you may need to find celt.dll by yourself. Make sure to have
a 64bit dll if your python is 64bit!

Some mumble servers require a certificate to work. You can generate one
by hand with eg. command 
`openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes`
Note that this certificate will only work for 365 days (see -days argument)!
When done, just tell the player to use them via the command line arguments.

# License

Licensed under MIT license. See LICENSE file for more details.
