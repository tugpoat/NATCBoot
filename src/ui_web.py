import os
import configparser
import signal
import string
import json
from bottle import Bottle, template, static_file, error, request, response, view
import beaker.middleware
from Database import ACNTBootDatabase
from GameList import *
from queues import ui_webq

session_opts = {
    'session.type': 'file',
    'session.cookie_expires': 300,
    'session.data_dir': './data',
    'session.auto': True
}

class UIWeb(Bottle):
    #TODO: The Web UI opening its own DB connection is not ideal.
    _db = None
    _games = None
    _prefs = None
    _bottle = None
    _beaker = None

    def __init__(self, name, gameslist, prefs):
        super(UIWeb, self).__init__()
        self._beaker = beaker.middleware.SessionMiddleware(self, session_opts)
        self.name = name
        self._games = gameslist
        self._prefs = prefs

        #set up routes
        self.route('/', method="GET", callback=self.index)
        self.route('/static/<filepath:path>', method="GET", callback=self.serve_static)
        self.route('/config', method="GET", callback=self.appconfig)
        self.route('/config', method="POST", callback=self.do_appconfig)
        self.route('/edit/<fhash>', method="GET", callback=self.edit)
        self.route('/edit/<fhash>', method="POST", callback=self.do_edit)
        self.route('/load/<node>/<fhash>', method="GET", callback=self.load)

    def start(self):
        self._db = ACNTBootDatabase('db.sqlite')
        self.run(host='0.0.0.0', port=8000, debug=False)

    def serve_static(self, filepath):
        if 'images/' in filepath and not os.path.isfile('static/'+filepath):
            return static_file('images/0.jpg', 'static')

        return static_file(filepath, 'static')

    def index(self):
        #FIXME
        filter_groups = self._db.getAttributes()
        filter_values = []
        filters = []
        if self._games != None:
            return template('index', games=self._games, filter_groups=filter_groups, filter_values=filter_values, activefilters=filters)
        else:
            return template('index')

    def auth(self):
        return

    def appconfig(self):        
        if self._prefs['Main']['skip_checksum'] == 'True':
            skip_checksum = 'checked'
        else:
            skip_checksum =  ''

        if self._prefs['Main']['gpio_reset'] == 'True':
            gpio_reset = 'checked'
        else:
            gpio_reset =  ''

        #TODO: default settings are stupid, make them go away. maybe load them from the system if not present in settings.cfg
        eth0_ip         =   self._prefs['Network']['eth0_ip']       or '192.168.0.1'
        eth0_netmask    =   self._prefs['Network']['eth0_netmask']  or '255.255.255.0'

        dimm_ip         =   self._prefs['Network']['dimm_ip']       or '192.168.0.2'

        wlan0_mode      =   self._prefs['Network']['wlan0_mode']    or 'AP'
        wlan0_ip        =   self._prefs['Network']['wlan0_ip']      or '10.0.0.1'
        wlan0_netmask   =   self._prefs['Network']['wlan0_netmask'] or '255.255.255.0'
        wlan0_ssid      =   self._prefs['Network']['wlan0_ssid']    or 'NAOMI'
        wlan0_psk       =   self._prefs['Network']['wlan0_psk']     or 'segarocks'

        games_directory =   self._prefs['Games']['directory']       or 'games'

        #render
        return template('config', skip_checksum=skip_checksum, gpio_reset=gpio_reset, eth0_ip=eth0_ip, eth0_netmask=eth0_netmask, wlan0_mode=wlan0_mode, wlan0_ip=wlan0_ip, wlan0_ssid=wlan0_ssid, wlan0_psk=wlan0_psk, wlan0_netmask=wlan0_netmask, dimm_ip=dimm_ip, games_directory=games_directory)
        
    def do_appconfig(self):
        skip_checksum   = request.forms.get('skip_checksum')
        gpio_reset      = request.forms.get('gpio_reset')


        if skip_checksum == 'on':
            skip_checksum = 'True'
        else:
            skip_checksum = 'False'

        if gpio_reset == 'on':
            gpio_reset = 'True'
        else:
            gpio_reset = 'False'

        self._prefs['Main']['skip_checksum']      =     skip_checksum
        self._prefs['Main']['gpio_reset']         =     gpio_reset

        #TODO: sanity checking on string values

        self._prefs['Network']['dimm_ip']         =     dimm_ip         =   request.forms.get('dimm_ip')

        self._prefs['Network']['eth0_ip']         =     eth0_ip         =   request.forms.get('eth0_ip')
        self._prefs['Network']['eth0_netmask']    =     eth0_netmask    =   request.forms.get('eth0_netmask')

        wlan0_mode = request.forms.get('wlan0_mode') 
        if wlan0_mode == 'wlan0_mode_client':
            wlan0_mode = 'Client'
        else:
            wlan0_mode = 'AP'

        #TODO: sanity checking on string values

        self._prefs['Network']['wlan0_mode']      =     wlan0_mode
        self._prefs['Network']['wlan0_ip']        =     wlan0_ip        =   request.forms.get('wlan0_ip')
        self._prefs['Network']['wlan0_netmask']   =     wlan0_netmask   =   request.forms.get('wlan0_netmask')
        self._prefs['Network']['wlan0_ssid']      =     wlan0_ssid      =   request.forms.get('wlan0_ssid')
        self._prefs['Network']['wlan0_psk']       =     wlan0_psk       =   request.forms.get('wlan0_psk')

        self._prefs['Games']['directory']         =     games_directory =   request.forms.get('games_directory')

        with open('settings.cfg', 'w') as prefs_file:
            self._prefs.write(prefs_file)

        #rework this thing for html
        if skip_checksum == 'True':
            skip_checksum = 'checked'
        else:
            skip_checksum = ''

        if gpio_reset == 'True':
            gpio_reset = 'checked'
        else:
            gpio_reset = ''

        return template('config', did_config=True, skip_checksum=skip_checksum, gpio_reset=gpio_reset, eth0_ip=eth0_ip, eth0_netmask=eth0_netmask, wlan0_mode=wlan0_mode, wlan0_ip=wlan0_ip, wlan0_ssid=wlan0_ssid, wlan0_psk=wlan0_psk, wlan0_netmask=wlan0_netmask, dimm_ip=dimm_ip, games_directory=games_directory)

    def apply_appconfig(self):
        #TODO: reconfigure network and stuff
        return

    def edit(self, fhash):
        g = None
        # we need to fetch the entire list of possible games for the user to select from
        gamelist = self._db.getGameList()

        g = [game for game in self._games if game.file_checksum == fhash][0]

        return template('edit', filename=g.filename, game_title=g.title, hashid=fhash, games_list=gamelist)

    def do_edit(self, fhash):
        new_game_id = request.forms.get('games')
        filename = request.forms.get('filename')
        self._db.editGame(new_game_id, filename, fhash)
        # Just rebuild the list for now
        # FIXME: replace the list entry with the updated one instead
        self._games = build_games_list(self._db, self._prefs)

        # FIXME: Maybe kick them back to the index instead of doing all this?
        g = None
        # we need to fetch the entire list of possible games for the user to select from
        gamelist = self._db.getGameList()

        g = [game for game in self._games if game.file_checksum == fhash][0]

        return template('edit', filename=g.filename, game_title=g.title, hashid=fhash, games_list=gamelist, did_edit=True)

    def load(self, node, fhash):
        #TODO: load on target node
        ui_webq.put(["LOAD", node, fhash])

    #TODO: other routes