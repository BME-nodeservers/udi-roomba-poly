#!/usr/bin/env python3
"""
This is a NodeServer for Wi-Fi enabled Roomba vacuums.

Originally written for Polyglot v2 by fahrer16 (Brian Feeney)

Updated for Polyglot v3 by Bob Paauwe
"""

import udi_interface
import asyncio
import sys
import json
import socket
import ssl
import struct
import time
import threading
from roomba import Roomba

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
aloop = None

STATES = {  "charge": 1, #"Charging"
            "new": 2, #"New Mission"
            "run": 3, #"Running"
            "resume":4, #"Running"
            "hmMidMsn": 5, #"Recharging"
            "recharge": 6, #"Recharging"
            "stuck": 7, #"Stuck"
            "hmUsrDock": 8, #"User Docking"
            "dock": 9, #"Docking"
            "dockend": 10, # "Docking - End Mission"
            "cancelled": 11, #"Cancelled"
            "stop": 12, #"Stopped"
            "pause": 13, #"Paused"
            "hmPostMsn": 14, #"End Mission"
            "": 0}

RUNNING_STATES = {2,3,4,5,6}

ERROR_MESSAGES = {
        0: "None",
        1: "Roomba is stuck with its left or right wheel hanging down.",
        2: "The debris extractors can't turn.",
        5: "The left or right wheel is stuck.",
        6: "The cliff sensors are dirty, it is hanging over a drop, "\
           "or it is stuck on a dark surface.",
        8: "The fan is stuck or its filter is clogged.",
        9: "The bumper is stuck, or the bumper sensor is dirty.",
        10: "The left or right wheel is not moving.",
        11: "Roomba has an internal error.",
        14: "The bin has a bad connection to the robot.",
        15: "Roomba has an internal error.",
        16: "Roomba has started while moving or at an angle, or was bumped "\
            "while running.",
        17: "The cleaning job is incomplete.",
        18: "Roomba cannot return to the Home Base or starting position."
    }

class asyncioThread(threading.Thread):
    """
    this class manages the asyncio event loop.
    """
    def __init__(self, *args, loop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loop = loop or asyncio.new_event_loop()
        self.running = False

    def run(self):
        self.running = True
        self.loop.run_forever()

    def run_method(self, method):
        return asyncio.run_coroutine_threadsafe(method, loop=self.loop)

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.join()
        self.running = False

class BasicRoomba(udi_interface.Node):
    """
    This is the Base Class for all Roombas as all Roomba's contain the features within.  Other Roomba's build upon these features.
    """
    def __init__(self, poly, primary, address, name, roomba):
        super().__init__(poly, primary, address, name)
        self.roomba = roomba
        self.quality = -1
        self.connected = False

        poly.subscribe(poly.START, self.start, address)
        poly.subscribe(poly.POLL, self.updateInfo)

    def start(self):
        self.updateInfo(polltype='shortPoll')

    def disconnect(self):
        LOGGER.info('Attempting to disconnect from Robot')
        if self.roomba:
            self.roomba.disconnect()

    def setOn(self, command):
        #Roomba Start Command (not to be confused with the node start command above)
        LOGGER.info('Received Start Command on %s', self.name)
        try:
            self.roomba.send_command("start")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Start Command on %s: %s', self.name, str(ex))
            return False

    def setOff(self, command):
        #Roomba Stop Command
        LOGGER.info('Received Stop Command on %s', self.name)
        try:
            self.roomba.send_command("stop")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Stop Command on %s: %s', self.name, str(ex))
            return False

    def setPause(self, command):
        #Roomba Pause Command
        LOGGER.info('Received Pause Command on %s', self.name)
        try:
            self.roomba.send_command("pause")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Pause Command on %s: %s', self.name, str(ex))
            return False

    def setResume(self, command):
        #Roomba Resume Command
        LOGGER.info('Received Resume Command on %s', self.name)
        try:
            self.roomba.send_command("resume")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Resume Command on %s: %s', self.name, str(ex))
            return False

    def setDock(self, command):
        #Roomba Dock Command
        LOGGER.info('Received Dock Command on %s', self.name)
        try:
            self.roomba.send_command("dock")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Dock Command on %s: %s', self.name, str(ex))
            return False

    def _updateBasicProperties(self):
        #LOGGER.debug('Setting Basic Properties for %s', self.name)

        #ST (On/Off)
        #GV1, States (Enumeration)
        try:
            _state = self.roomba.master_state["state"]["reported"]["cleanMissionStatus"]["phase"]
            LOGGER.debug('Current state on %s: %s', self.name, str(_state))
            if _state in STATES:
                self.setDriver('GV1', STATES[_state])
                _running = (STATES[_state] in RUNNING_STATES)
                self.setDriver('ST', (0,100)[int(_running)])
        except Exception as ex:
            LOGGER.error("Error updating current state on %s: %s", self.name, str(ex))

        #GV2, Connected (True/False)
        try:
            _connected = self.roomba.roomba_connected
            if _connected == False and self.connected == True:
                LOGGER.error('Roomba Disconnected: %s', self.name)
            elif _connected == True and self.connected == False:
                LOGGER.info('Roomba Connected: %s', self.name)
            self.connected = _connected

            self.setDriver('GV2', int(_connected))

        except Exception as ex:
            LOGGER.error("Error updating connection status on %s: %s", self.name, str(ex))

        #BATLVL, Battery (Percent)
        try:
            _batPct = self.roomba.master_state["state"]["reported"]["batPct"]
            self.setDriver('BATLVL', _batPct)
        except Exception as ex:
            LOGGER.error("Error updating battery Percentage on %s: %s", self.name, str(ex))

        #GV3, Bin Present (True/False)
        try:
            _binPresent = self.roomba.master_state["state"]["reported"]["bin"]["present"]
            self.setDriver('GV3', int(_binPresent))
        except Exception as ex:
            LOGGER.error("Error updating Bin Present on %s: %s", self.name, str(ex))

        #GV4, Wifi Signal (Percent)
        try:
            _rssi = self.roomba.master_state["state"]["reported"]["signal"]["rssi"]
            _quality = int(max(min(2.* (_rssi + 100.),100),0))
            if abs(_quality - self.quality) > 15: #Quality can change very frequently, only update ISY if it has changed by more than 15%
                self.setDriver('GV4', _quality)
                self.quality = _quality
        except Exception as ex:
            LOGGER.error(f"Error updating WiFi Signal Strength on {self.name}: {ex}")

        #GV5, Runtime (Hours)
        try:
            _hr = self.roomba.master_state["state"]["reported"]["bbrun"]["hr"]
            _min = self.roomba.master_state["state"]["reported"]["bbrun"]["min"]
            _runtime = round(_hr + _min/60.,1)
            self.setDriver('GV5', _runtime)
        except Exception as ex:
            LOGGER.error("Error updating runtime on %s: %s", self.name, str(ex))

        #GV6, Error Actie (True/False)
        #ALARM, Error (Enumeration)
        try:
            if "error" in self.roomba.master_state["state"]["reported"]["cleanMissionStatus"]:
                _error = self.roomba.master_state["state"]["reported"]["cleanMissionStatus"]["error"]
            else: _error = 0

            self.setDriver('GV6', int(_error != 0))
            self.setDriver('ALARM', _error)
        except Exception as ex:
            LOGGER.error("Error updating current Error Status on %s: %s", self.name, str(ex))
    
    def delete(self):
        try:
            LOGGER.info("Deleting %s and attempting to stop communication to roomba", self.name)
            self.roomba.disconnect()
        except Exception as ex:
            LOGGER.error("Error attempting to stop communication to %s: %s", self.name, str(ex))

    def updateInfo(self, polltype):
        if polltype == 'shortPoll':
            self._updateBasicProperties()

    def query(self, command=None):
        self.updateInfo(polltype='shortPoll')
        self.reportDrivers()


    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25} #Current Error (Enumeration)
               ]
    id = 'basicroomba'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query
                }

class Series800Roomba(BasicRoomba):
    """
    This class builds upon the BasicRoomba class by adding full bin detection present in the 800 series roombas
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _update800SeriesProperties(self):
        #LOGGER.debug('Setting Bin status and settings for %s', self.name)

        #GV7, Bin Full (True/False)
        try:
            _binFull = self.roomba.master_state["state"]["reported"]["bin"]["full"]
            self.setDriver('GV7', int(_binFull))
        except Exception as ex:
            LOGGER.error("Error updating Bin Full on %s: %s", self.name, str(ex))

        #GV8, Behavior on Full Bin (Enumeration, 1=Finish, 0=Continue)
        try:
            _finishOnBinFull = self.roomba.master_state["state"]["reported"]["binPause"]
            self.setDriver('GV8', int(_finishOnBinFull))
        except Exception as ex:
            LOGGER.error("Error updating Behavior on Bin Full Setting on %s: %s", self.name, str(ex))

    def updateInfo(self, polltype):
        super().updateInfo(polltype)
        self._update800SeriesProperties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        LOGGER.info('Received Command to set Bin Finish on %s: %s', self.name, str(command))
        try:
            _setting = command.get('value')
            self.roomba.set_preference("binPause", ("false","true")[int(_setting)]) # 0=Continue, 1=Finish
        except Exception as ex:
            LOGGER.error("Error setting Bin Finish Parameter on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25} #Behavior on Full Bin (Enumeration - Finish/Continue)
               ]
    id = 'series800roomba'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish
                }

class Series900Roomba(Series800Roomba):
    """
    This class builds upon the Series800Roomba class by adding position tracking present in the 900 series roombas
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _update900SeriesProperties(self):
        #LOGGER.debug('Setting Position status for %s', self.name)

        #GV9, X Position
        try:
            _x = self.roomba.master_state["state"]["reported"]["pose"]["point"]["x"]
            self.setDriver('GV9', int(_x))
        except Exception as ex:
            LOGGER.error("Error updating X Position on %s: %s", self.name, str(ex))

        #GV10, Y Position
        try:
            _y = self.roomba.master_state["state"]["reported"]["pose"]["point"]["y"]
            self.setDriver('GV10', int(_y))
        except Exception as ex:
            LOGGER.error("Error updating Y Position on %s: %s", self.name, str(ex))

        #ROTATE, Theta (degrees)
        try:
            _theta = self.roomba.master_state["state"]["reported"]["pose"]["theta"]
            self.setDriver('ROTATE', int(_theta))
        except Exception as ex:
            LOGGER.error("Error updating Theta Position on %s: %s", self.name, str(ex))

        #LOGGER.debug('Getting Passes setting for %s', self.name)

        #GV11, Passes Setting (0="", 1=One, 2=Two, 3=Automatic)
        try:
            _noAutoPasses = self.roomba.master_state["state"]["reported"]["noAutoPasses"]
            _twoPass = self.roomba.master_state["state"]["reported"]["twoPass"]
            if not _noAutoPasses:
                self.setDriver('GV11', 3)
            elif _twoPass:
                self.setDriver('GV11', 2)
            else:
                self.setDriver('GV11', 1)
        except Exception as ex:
            LOGGER.error("Error updating Passes Setting on %s: %s", self.name, str(ex))

        #GV12, Edge Clean (On/Off)
        try:
            _openOnly = self.roomba.master_state["state"]["reported"]["openOnly"]
            self.setDriver('GV12', (100,0)[int(_openOnly)]) #note 0,100 order (openOnly True means Edge Clean is Off)
        except Exception as ex:
            LOGGER.error("Error updating Edge Clean Setting on %s: %s", self.name, str(ex))


    def updateInfo(self, polltype):
        super().updateInfo(polltype)
        self._update900SeriesProperties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setBinFinish(command)

    def setPasses(self,command=None):
        LOGGER.info('Received Command to set Number of Passes on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            if _setting == 1: #One Pass
                self.roomba.set_preference("noAutoPasses", "true")
                self.roomba.set_preference("twoPass", "false")
            elif _setting == 2: #Two Passes
                self.roomba.set_preference("noAutoPasses", "true")
                self.roomba.set_preference("twoPass", "true")
            elif _setting == 3: #Automatic Passes
                self.roomba.set_preference("noAutoPasses", "false")
        except Exception as ex:
            LOGGER.error("Error setting Number of Passes on %s: %s", self.name, str(ex))

    def setEdgeClean(self,command=None):
        LOGGER.info('Received Command to set Edge Clean on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            if _setting == 100:
                self.roomba.set_preference("openOnly", "false")
            else:
                self.roomba.set_preference("openOnly", "true")
        except Exception as ex:
            LOGGER.error("Error setting Edge Clean on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25}, #Behavior on Full Bin (Enumeration - Finish/Continue)
               {'driver': 'GV9', 'value': 0, 'uom': 56}, #X Position (Raw Value)
               {'driver': 'GV10', 'value': 0, 'uom': 56}, #Y Position (Raw Value)
               {'driver': 'ROTATE', 'value': 0, 'uom': 14}, #Theta (Degrees)
               {'driver': 'GV11', 'value': 0, 'uom': 25}, #Passes Setting (Enumeration, One/Two/Automatic)
               {'driver': 'GV12', 'value': 0, 'uom': 78} #Edge Clean (On/Off)
               ]
    id = 'series900roomba'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish, 'SET_PASSES': setPasses, 'SET_EDGE_CLEAN': setEdgeClean
                }

class Roomba980(Series900Roomba):
    """
    This class builds upon the Series900Roomba class by adding fan settings (Carpet Boost)
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _update980Properties(self):
        #LOGGER.debug('Updating status for Roomba 980 %s', self.name)

        #GV13, Fan Speed Setting (0="", 1=Eco, 2=Automatic, 3=Performance)
        try:
            _carpetBoost = self.roomba.master_state["state"]["reported"]["carpetBoost"]
            _vacHigh = self.roomba.master_state["state"]["reported"]["vacHigh"]
            if _carpetBoost:
                self.setDriver('GV13', 2)
            elif _vacHigh:
                self.setDriver('GV13', 3)
            else:
                self.setDriver('GV13', 1)
        except Exception as ex:
            LOGGER.error("Error updating Fan Speed Setting on %s: %s", self.name, str(ex))

    def updateInfo(self, polltype):
        super().updateInfo(polltype)
        self._update980Properties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setBinFinish(command)

    def setPasses(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPasses(command)

    def setEdgeClean(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setEdgeClean(command)

    def setFanSpeed(self,command=None): 
        LOGGER.info('Received Command to set Fan Speed on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            #(0="", 1=Eco, 2=Automatic, 3=Performance)
            if _setting == 1: #Eco
                LOGGER.info('Setting %s fan speed to "Eco"', self.name)
                self.roomba.set_preference("carpetBoost", "false")
                self.roomba.set_preference("vacHigh", "false")
            elif _setting == 2: #Automatic
                LOGGER.info('Setting %s fan speed to "Automatic" (Carpet Boost Enabled)', self.name)
                self.roomba.set_preference("carpetBoost", "true")
                self.roomba.set_preference("vacHigh", "false")
            elif _setting == 3: #Performance
                LOGGER.info('Setting %s fan speed to "Perfomance" (High Fan Speed)', self.name)
                self.roomba.set_preference("carpetBoost", "false")
                self.roomba.set_preference("vacHigh", "true")
        except Exception as ex:
            LOGGER.error("Error setting Number of Passes on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25}, #Behavior on Full Bin (Enumeration - Finish/Continue)
               {'driver': 'GV9', 'value': 0, 'uom': 56}, #X Position (Raw Value)
               {'driver': 'GV10', 'value': 0, 'uom': 56}, #Y Position (Raw Value)
               {'driver': 'ROTATE', 'value': 0, 'uom': 14}, #Theta (Degrees)
               {'driver': 'GV11', 'value': 0, 'uom': 25}, #Passes Setting (Enumeration, One/Two/Automatic)
               {'driver': 'GV12', 'value': 0, 'uom': 78}, #Edge Clean (On/Off)
               {'driver': 'GV13', 'value': 0, 'uom': 25} #Fan Speed Setting (Enumeration)
               ]
    id = 'roomba980'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish, 'SET_PASSES': setPasses, 'SET_EDGE_CLEAN': setEdgeClean, 'SET_FAN_SPEED': setFanSpeed
                }

class Roombai7(Series900Roomba):
    """
    This class builds upon the Series900Roomba class 
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _updatei7Properties(self):
        #LOGGER.debug('Updating status for Roomba i7 %s', self.name)

        #GV13, Fan Speed Setting (0="", 1=Eco, 2=Automatic, 3=Performance)
        try:
            _carpetBoost = self.roomba.master_state["state"]["reported"]["carpetBoost"]
            _vacHigh = self.roomba.master_state["state"]["reported"]["vacHigh"]
            if _carpetBoost:
                self.setDriver('GV13', 2)
            elif _vacHigh:
                self.setDriver('GV13', 3)
            else:
                self.setDriver('GV13', 1)
        except Exception as ex:
            LOGGER.error("Error updating Fan Speed Setting on %s: %s", self.name, str(ex))

    def updateInfo(self, polltype):
        super().updateInfo(polltype)
        self._updatei7Properties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setBinFinish(command)

    def setPasses(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPasses(command)

    def setEdgeClean(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setEdgeClean(command)

    def setFanSpeed(self,command=None): 
        LOGGER.info('Received Command to set Fan Speed on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            #(0="", 1=Eco, 2=Automatic, 3=Performance)
            if _setting == 1: #Eco
                LOGGER.info('Setting %s fan speed to "Eco"', self.name)
                self.roomba.set_preference("carpetBoost", "false")
                self.roomba.set_preference("vacHigh", "false")
            elif _setting == 2: #Automatic
                LOGGER.info('Setting %s fan speed to "Automatic" (Carpet Boost Enabled)', self.name)
                self.roomba.set_preference("carpetBoost", "true")
                self.roomba.set_preference("vacHigh", "false")
            elif _setting == 3: #Performance
                LOGGER.info('Setting %s fan speed to "Perfomance" (High Fan Speed)', self.name)
                self.roomba.set_preference("carpetBoost", "false")
                self.roomba.set_preference("vacHigh", "true")
        except Exception as ex:
            LOGGER.error("Error setting Number of Passes on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25}, #Behavior on Full Bin (Enumeration - Finish/Continue)
               {'driver': 'GV9', 'value': 0, 'uom': 56}, #X Position (Raw Value)
               {'driver': 'GV10', 'value': 0, 'uom': 56}, #Y Position (Raw Value)
               {'driver': 'ROTATE', 'value': 0, 'uom': 14}, #Theta (Degrees)
               {'driver': 'GV11', 'value': 0, 'uom': 25}, #Passes Setting (Enumeration, One/Two/Automatic)
               {'driver': 'GV12', 'value': 0, 'uom': 78}, #Edge Clean (On/Off)
               {'driver': 'GV13', 'value': 0, 'uom': 25} #Fan Speed Setting (Enumeration)
               ]
    id = 'roombai7'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish, 'SET_PASSES': setPasses, 'SET_EDGE_CLEAN': setEdgeClean, 'SET_FAN_SPEED': setFanSpeed
               }

control = None
polyglot = None
robots = {}
configured = False

def _get_response(sock, roomba_message):
    try:
        while True:
            raw_response, addr = sock.recvfrom(1024)

            LOGGER.debug("Received response: %s, address: %s", raw_response, addr)
            data = raw_response.decode()

            LOGGER.info(f'Comparing {data} with {roomba_message}')
            if data == roomba_message:
                continue

            json_response = json.loads(data)
            if "Roomba" in json_response["hostname"] or "iRobot" in json_response["hostname"]:
                return {
                        'hostname':json_response["hostname"],
                        'robot_name':json_response["robotname"],
                        'ip':json_response["ip"],
                        'mac':json_response["mac"],
                        'firmware':json_response["sw"],
                        'sku':json_response["sku"],
                        'blid': json_response["hostname"].split('-')[1],
                        'capabilities':json_response["cap"],
                        }

    except socket.timeout:
        #LOGGER.error("Socket timeout")
        LOGGER.error("Socket timeout while waiting for response")
        return None
    except Exception as e:
        LOGGER.error(f'Error while waiting for response {e}')
        return None


def discover():
    global polyglot
    global robots

    LOGGER.info(f'Attempting to discover Roombas')
    nw_int = polyglot.getNetworkInterface()
    udp_bind_address = ""
    udp_address = nw_int['broadcast']
    udp_port = 5678
    roomba_message = "irobotmcs"
    amount_of_broadcasted_messages = 5
    robots = {}

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    server_socket.setsockopt(socket.IPPROTO_IP, 23, 1) # HACK 23 = IP_ONESBCAST
    server_socket.settimeout(7)

    # start server
    server_socket.bind((udp_bind_address, udp_port))
    LOGGER.debug(f'Socket server started, ip {udp_bind_address} port {udp_port}')

    # broadcast message and get responses
    for i in range(amount_of_broadcasted_messages):
        try:
            LOGGER.debug(f'broadcasting to bcast address {udp_address}')
            server_socket.sendto(roomba_message.encode(), (udp_address, udp_port))

            # get response
            response = _get_response(server_socket, roomba_message)
            if response is not None:
                robots[response['ip']] = response
                LOGGER.debug(f'Found robot {response["robot_name"]}')
                LOGGER.debug(response)
                #server_socket.close()
                #return

            time.sleep(1)

        except Exception as e:
            LOGGER.error(f'Discover error: {e}')

    server_socket.close()
    LOGGER.error('Failed to discover any Roomba robots')

def getPassword(robot):
    global polyglot

    message = bytes.fromhex("f005efcc3b2900")
    roomba_port = 8883

    polyglot.Notices['passwd'] = f'With the robot {robot["robot_name"]} at the base station, press and hold the Home button until the wi-fi light flashes'

    """
    Roomba have to be on Home Base powered on.
    Press and hold HOME button until you hear series of tones.
    Release button, Wi-Fi LED should be flashing
    After that execute get_password method
    """

    while True:
        LOGGER.info(f'start password discovery')
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.settimeout(10)
        ssl_socket = ssl.wrap_socket(
            server_socket,
            ssl_version=ssl.PROTOCOL_TLS,
            ciphers="DEFAULT@SECLEVEL=1",
            0x04,
        )

        try:
            LOGGER.info(f'Connecting to {robot["ip"]} on port {roomba_port}')
            ssl_socket.connect((robot['ip'], roomba_port))
            ssl_socket.send(message)
        except Exception as e:
            LOGGER.error(f'Failed to connect to robot: {e}')
            ssl_socket.close()
            time.sleep(5)
            continue

        try:
            LOGGER.info('Waiting for response from robot')
            response = _get_pw_response(ssl_socket)
            password = str(response[7:].decode().rstrip("\x00"))
            if password != '':
                robot['password'] = password
                LOGGER.info(f'Found password {password}')
                ssl_socket.close()
                break
            else:
                ssl_socket.close()
                time.sleep(5)

        except Exception as e:
            LOGGER.error(f'Error: problem getting password: {e}')
            ssl_socket.close()
            break



def _get_pw_response(sock):
    try:
        raw_data = b""
        response_length = 35
        while True:
            if len(raw_data) >= response_length + 2:
                break

            response = sock.recv(1024)

            if len(response) == 0:
                break

            raw_data += response
            if len(raw_data) >= 2:
                response_length = struct.unpack("B", raw_data[1:2])[0]
        sock.close()
        return raw_data
    except socket.timeout:
        LOGGER.error("Socket timeout")
        return None
    except socket.error as e:
        LOGGER.error("Socket error", e)
        return None


def _getCapability(roomba, capability):
    '''
    If a capability is not contained within the roomba's master_state, 
    it doesn't have that capability.  Not sure it could ever be set to 0,
    but this will ensure it is 1 in order to report it has the capability
    '''
    try:
        return roomba.master_state["state"]["reported"]["cap"][capability] >= 1
    except:
        return False

def handleRobotData(data):
    global customData
    global robots

    # customData will hold the list of found robots.
    LOGGER.info(f'Loading saved robots {data}')
    customData.load(data)

    try:
        robots = customData['robots']
        if type(robots) is dict:
            LOGGER.info(f'We have restored the saved robot list')
        else:
            robots = {}
    except Exception as e:
        LOGGER.warning('No robots defined in custom data')

    LOGGER.info('Finished with handleRobotData')

def handleConfigDone():
    global polyglot
    global robots
    global configured

    if len(robots.keys()) == 0:
        LOGGER.info('No saved robots...')
        discoverRobots()

    polyglot.Notices.clear()

    configured = True

async def wait_for_state(_roomba):
    while 'state' not in _roomba.master_state:
        LOGGER.info(f'Waiting for data to populate {_roomba.master_state}')
        await asyncio.sleep(1)

    while 'reported' not in _roomba.master_state['state']:
        await asyncio.sleep(1)

async def addNodes(robots):
    global polyglot
    global aloop

    LOGGER.info(f'Discovery fround {len(robots)} robots!')
    for robot in robots.values():
        polyglot.Notices['setup'] = f'Initializing connection to {robot["robot_name"]}'
        LOGGER.info(f'Create a new node for {robot["robot_name"]} ...')

        _name = robot['robot_name']
        _address = 'rm' + robot['blid'][-10:].lower()

        # Create a Roomba object and connect to robot
        LOGGER.info(f'Create Roomba Object')
        _roomba = Roomba(robot['ip'], robot['blid'], robot['password'], roombaName=robot['robot_name'], log=LOGGER)
        LOGGER.info(f'Connecting to robot ...')
        await _roomba.connect()

        await asyncio.create_task(wait_for_state(_roomba))

        if len(_roomba.master_state["state"]["reported"]["cap"]) > 0:
            LOGGER.info(f'Here is where we reall create the node')
            try:
                if polyglot.getNode(_address):
                    polyglot.getNode(_address).roomba = _roomba
                    LOGGER.info(f'_name already exist, skipping.')
                    continue

                LOGGER.debug(f'Getting capabilities from {_name}')
                _hasPos = _getCapability(_roomba, 'pose')
                _hasCarpetBoost = _getCapability(_roomba, 'carpetBoost')
                _hasBinFullDetect = _getCapability(_roomba, 'binFullDetect')
                _hasDockComm = _getCapability(_roomba, 'dockComm')
                LOGGER.debug(f'Capabilities: Position: {_hasPos}, CarpetBoost: {_hasCarpetBoost}, BinFullDetection: {_hasBinFullDetect}')

                LOGGER.info(f'pick the right node class depending on capabilities')
                if  _hasDockComm:
                    LOGGER.info(f'Adding Roomba i7: {_name} ({_address})')
                    polyglot.addNode(Roombai7(polyglot, _address, _address, _name, _roomba))
                elif  _hasCarpetBoost:
                    LOGGER.info(f'Adding Roomba 980: {_name} ({_address})')
                    polyglot.addNode(Roomba980(polyglot, _address, _address, _name, _roomba))
                elif _hasPos:
                    LOGGER.info(f'Adding Series 900 Roomba: {_name} ({_address})')
                    polyglot.addNode(Series900Roomba(polyglot, _address, _address, _name, _roomba))
                elif _hasBinFullDetect:
                    LOGGER.info(f'Adding Series 800 Roomba: {_name} ({_address})')
                    polyglot.addNode(Series800Roomba(polyglot, _address, _address, _name, _roomba))
                else:
                    LOGGER.info(f'Adding Base Roomba: {_name} ({_address})')
                    polyglot.addNode(BasicRoomba(polyglot, _address, _address, _name, _roomba))
            except Exception as ex:
                LOGGER.error(f'Error adding {_name} after discovery: {ex}')
        else:
            LOGGER.debug(f'Information not yet received for {_name}')

        polyglot.Notices.clear()

def discoverRobots():
    global polyglot
    global robots
    global customData
    global configured
    global aloop

    # make sure we disconnect from the Roomba
    for node in polyglot.nodes():
        node.disconnect()
    configured = False

    discover()

    for robot in robots.values():
        if 'password' not in robot or robot['password'] == '':
            getPassword(robot)

    customData['robots'] = robots

async def _start_the_nodes(robots):
    await addNodes(robots)

def userDiscover():
    global robots
    global aloop
    global configured

    discoverRobots()

    polyglot.Notices.clear()

    if len(robots.keys()) == 0:
        LOGGER.warning(f'No robots discovered.')
        return

    configured = True
    aloop.run_method(addNodes(robots))

async def start():
    global robots
    global configured

    LOGGER.info('Roomba node server starting')
    # make sure configure is done
    while not configured:
        time.sleep(5)

    await addNodes(robots)

if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start('2.0.8')

        customData = Custom(polyglot, 'customdata')
        #control = Controller(polyglot)

        # Add subscriptions for CONFIGDONE and CUSTOMDATA
        polyglot.subscribe(polyglot.CUSTOMDATA, handleRobotData)
        polyglot.subscribe(polyglot.CONFIGDONE, handleConfigDone)
        polyglot.subscribe(polyglot.DISCOVER, userDiscover)
        
        polyglot.updateProfile()
        polyglot.setCustomParamsDoc()

        # Create a background thread to run the event loop
        aloop = asyncioThread()
        aloop.start()

        polyglot.ready()

        aloop.run_method(start())

        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        aloop.stop()
        sys.exit(0)
