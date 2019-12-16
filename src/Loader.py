import os
import time
import json
import configparser
from multiprocessing import Manager, Process, Queue
from mbus import *
from NodeDescriptor import *
from GameDescriptor import *
from NetComm import *

from loader_events import *


'''
STATUS CODES
-1 error
0 unused
1 connecting
2 uploading
3 booting
4 keep-alive

RETURN CODES
0 success
1 error
'''



'''
The actual loader. Attached to a NodeDescriptor in practical use, and runs as its own process.

TODO: run a ping against the NetDIMM. if it breaks, then restart the netboot cycle once reachable to maintain the desired state. 
This will effectively give us single-game functionality without compromise.
'''
class LoadWorker(Process):
    mq = None
    path = None
    host = None
    port = None
    _comm = None
    _active = False

    '''
    Construct using bare minimum of information
    queue: Queue, for passing messages back to the main process
    abs_path: String, absolute path of ROM file
    host: String, IP Address of endpoint
    '''
    def __init__(self, queue, abs_path, host, port):
        super(LoadWorker, self).__init__()
        self.mq = queue
        self.path = abs_path
        self.host = host
        self.port = port
        self._comm = NetComm()

    def is_active(self):
        return _active

    '''
    This is the function that does the actual work.
    It is invoked with LoadWorker.start() and runs until terminated.
    '''
    def run(self):
        filename = self.path[:(len(self.path) - self.path.rfind(os.pathsep))]
        
        # Open a connection to endpoint and notify the main thread that we are doing so.
        try:
            MBus.handle(Node_LoaderStatusCodeMessage(payload=LoaderStatus(1)))
            self._comm.connect(self.host, self.port)
        except Exception as ex:
            MBus.handle(Node_LoaderStatusCodeMessage(payload=LoaderStatus(-1)))
            #print(("%s : connection to %s failed! exiting." % (self.name, self.host)))
            return 1

        # We have successfully connected to the endpoint. Let's shove our rom file down its throat.
        try:
            MBus.handle(Node_LoaderStatusCodeMessage(payload=LoaderStatus(2)))

            self.uploadrom(game_path)

            message = [3, ("%s : Booting " % (self.name, self.path, self.host))]
            MBus.handle(Node_LoaderStatusCodeMessage(payload=LoaderStatus(3)))

            # restart the endpoint system, this will boot into the game we just sent
            self._comm.HOST_Restart()

        except Exception as ex:
            MBus.handle(Node_LoaderExceptionMessage(payload=("%s : Error booting game on hardware! ex: %s" % (self.name, self.path, self.host, repr(ex)))))
            MBus.handle(Node_LoaderStatusCodeMessage(payload=LoaderStatus(0)))
            return 1

        self._active = True

        message = [4, ("%s : Entering Keep-alive loop. " % (self.name))]
        MBus.handle(Node_LoaderStatusCodeMessage(payload=LoaderStatus(4)))
        keepalive()

    def uploadrom(self, rom_path):
        self._comm.HOST_SetMode(0, 1)
        # disable encryption by setting magic zero-key
        self._comm.SECURITY_SetKeycode("\x00" * 8)

        # uploads file. Also sets "dimm information" (file length and crc32)
        self._comm.DIMM_UploadFile(rom_path, None, upload_pct_callback)
    
    def upload_pct_callback(percent_complete):
        #TODO: deliver this number to UI and/or main thread via messagebus
        print("upload cb: " + percent_complete + "%")

    def keepalive(self):
        '''
        Some systems and games have some wacky time limit thing where they will stop working after a period of time.
        We get around this by sending a heartbeat to the endpoint.
        '''
        while 1:
            try:
                if not self.mq.empty():
                    witem = ui_webq.get(False)
                    if witem[0] == "die":
                        self.mq.put([0, ("%s : Received termination request. Aborting keep-alive, disconnecting and returning to idle." % (self.name, self.path, self.host))])
                        self._comm.disconnect()
                        return

                # set time limit to 10h. According to some reports, this does not work.
                TIME_SetLimit(10*60*1000)
                time.sleep(5)
            except Exception as ex:
                #TODO: maybe check what the exception is and automatically determine whether or not to continue
                message = [-1, ("%s : Keep-alive failed! Continuing to attempt anyway." % (self.name, self.path, self.host)), repr(ex)]
                self.mq.put(message)
