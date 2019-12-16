from multiprocessing import Manager, Process
from asyncio import *
import time
import configparser

from Database import ACNTBootDatabase
from NodeDescriptor import NodeDescriptor, NodeList
from GameDescriptor import GameDescriptor
from GameList import *
from Loader import LoadWorker
from ui_web import UIWeb
from sysctl import *
from gpio_reboot import *
from queues import *
from mbus import *

#FIXME: FUCK THIS ENTIRE FILE

#Message handlers

def cb_gpio_reset():
	print("got message")
	GPIO_Reboot();

# load settings
PREFS_FILE = "settings.cfg"
prefs = configparser.ConfigParser()
prefs_file = open(PREFS_FILE, 'r')
prefs.read_file(prefs_file)
prefs_file.close()

#TODO: if file/directory does not exist, copy a default from the read-only partition to the SD card.

# set up database
db = ACNTBootDatabase('db.sqlite')

#set up game list
games_list = GameList(prefs['Directories']['cfg_dir'], prefs['Directories']['games_dir'])
games_list.scanForNewGames(db)

#set up node list
nodes = NodeList(prefs['Directories']['nodes_dir'])
nodes.loadNodes()

# TODO: set up adafruit ui if detected and enabled

# Launch web UI
app = UIWeb('Web UI', games_list, nodes, prefs)
app._games = games_list
app.list_loaded = True
t = Process(target=app.start)
t.start()


# Main loop
# Handles messaging between loaders, etc. and the main thread/UI instances

#TODO: FUCK THIS THING
while 1:
	try:

		#FIXME: Kinda works. finish implementation of messaging. needs to be more asynchronous in its fetches.
		if not ui_webq.empty():
			witem = ui_webq.get(False)
			print(witem)
			if witem[0] == 'LOAD':
				#FIXME: Check to see if we're already running something on whatever node has been specified and then kill it if yes
				newgame = None

				#make sure that the requested node is valid
				if int(witem[1]) < len(nodes) and int(witem[1]) > -1:
					for g in games_list:
						if g.file_checksum == witem[2]:
							newgame = g
							break
					#set up loader
					print(newgame.title)

					nodes[int(witem[1])].load(loaderq, newgame)

					nodes.saveNodes()

					ui_webq.task_done()
				else:
					print('requested node out of range')

			#system control functions	
			elif witem[0] == 'gpio':
				if witem[1] == 'reset':
					GPIO_Reboot()
			elif witem[0] == 'sysctl':
				# Ideally we would do some kind of mapping in here so we don't need a giant if structure 
				# but I'm going to be lazy for now and clean it up later
				if witem[1] == 'reboot':
					reboot_system()
				elif witem[1] == 'shutdown':
					shutdown_system()
				elif witem[1] == 'writeappconfig':
					exit()
					#remount configs/roms partition rw
					#write config
					#remount configs/roms partition ro
				elif witem[1] == 'writesysconfig':
					remount_root_rw()
					#TODO: Write config
					remount_root_ro()
				elif witem[1] == 'sshd_en':
					enable_sshd()
				elif witem[1] == 'sshd_dis':
					disable_sshd()

		if not loaderq.empty():
			loader_item = loaderq.get(False)
			print(loader_item)

	except Exception as e:
		print(str(e))
		pass
