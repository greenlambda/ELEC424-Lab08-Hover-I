#!/usr/bin/env python

# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.

"""
Driver for reading data from the PyGame API. Used from Inpyt.py for reading input data.
Hacked to include AI 

You will need to modify the following files as shown below
+++ b/lib/cfclient/ui/main.py   
-        self.joystickReader = JoystickReader()
+        self.joystickReader = JoystickReader(cf=self.cf)


+++ b/lib/cfclient/utils/input.py   
+from cfclient.utils.aicontroller import AiController 

-    def __init__(self, do_device_discovery=True):
+    def __init__(self, do_device_discovery=True, cf=None):

-        self.inputdevice = PyGameReader()
+        self.inputdevice = AiController(cf)

You will also need to map the "exit" button to your controller.  This will server as 
the on/off switch for the AI.

You will also likely have to open the tools->parameters tab in the PC-Client which will load the TOC.  

"""

__author__ = 'Steven Arroyo'
__all__ = ['AiController']

import pygame
from pygame.locals import *

import time
import logging

logger = logging.getLogger(__name__)

class AiController():
    """Used for reading data from input devices using the PyGame API."""
    def __init__(self,cf):
        self.cf = cf
        self.inputMap = None
        pygame.init()

        # AI variables
        self.timer1 = 0
        self.lastTime = 0
        self.lastParamTime = 0

        # ---AI tuning variables---
        # This is the thrust of the motors duing hover.  0.5 reaches ~1ft depending on battery
        self.maxThrust = 0.6
        self.minLandThrust = 0.35
        # Determines how fast to take off
        self.takeoffTime = 0.5
        # Determines how fast to land
        self.landTime = 3
        # The hover time
        self.hoverTime = 5
        # Sets the delay between test flights
        self.repeatDelay = 5

        # parameters pulled from json with defaults from crazyflie pid.h
        # perl -ne '/"(\w*)": {/ && print $1,  "\n" ' lib/cflib/cache/27A2C4BA.json
        self.cfParams = {
            'pid_rate.pitch_kp': 70.0, 
            'pid_rate.pitch_kd': 0.0, 
            'pid_rate.pitch_ki': 0.0, 
            'pid_rate.roll_kp': 70.0,
            'pid_rate.roll_kd': 0.0, 
            'pid_rate.roll_ki': 0.0, 
            'pid_rate.yaw_kp': 50.0, 
            'pid_rate.yaw_kd': 0.0, 
            'pid_rate.yaw_ki': 25.0, 
            'pid_attitude.pitch_kp': 3.5, 
            'pid_attitude.pitch_kd': 0.0, 
            'pid_attitude.pitch_ki': 6.0, 
            'pid_attitude.roll_kp': 3.5, 
            'pid_attitude.roll_kd': 0.0, 
            'pid_attitude.roll_ki': 6.0, 
            'pid_attitude.yaw_kp': 0.0, 
            'pid_attitude.yaw_kd': 0.0, 
            'pid_attitude.yaw_ki': 0.0, 
            'sensorfusion6.kp': 0.800000011921, 
            'sensorfusion6.ki': 0.00200000009499, 
            'imu_acc_lpf.factor': 32,
            'altHold.kd': 0.01,
            'altHold.ki': 0.08,
            'altHold.kp': 0.05,
            'altHold.hoverKd': 0.01,
            'altHold.hoverKi': 0.1,
            'altHold.hoverKp': 0.5,
            'altHold.altEstKp1': 0.8,
            'altHold.altEstKp2': 1.0,
            'altHold.altEstKi': 0.001
            }

        # Add a callback once the crazyflie is fully connected to update
        # these parameters
        self.cf.connected.add_callback(lambda uri: self._update_all_parameters(uri))

    def _update_all_parameters(self, uri):
        logger.info("Updating parameters on [%s]", uri)
        for p in self.cfParams:
            self.updateCrazyFlieParam(p)        

    def start_input(self, deviceId, inputMap):
        """Initalize the reading and open the device with deviceId and set the mapping for axis/buttons using the
        inputMap"""
        self.data = {"roll":0.0, "pitch":0.0, "yaw":0.0, "thrust":0.0, "pitchcal":0.0, "rollcal":0.0, "estop": False, "exit":False, "althold":False}
        self.aiData = {"roll":0.0, "pitch":0.0, "yaw":0.0, "thrust":0.0, "pitchcal":0.0, "rollcal":0.0, "estop": False, "exit":False, "althold":False}
        self.inputMap = inputMap
        self.j = pygame.joystick.Joystick(deviceId)
        self.j.init()

    def read_input(self):
        """Read input from the selected device.
        # First we read data from controller as normal
        # ----------------------------------------------------
        # We only want the pitch/roll cal to be "oneshot", don't
        # save this value.
        """

        self.data["pitchcal"] = 0.0
        self.data["rollcal"] = 0.0
        for e in pygame.event.get():
          if e.type == pygame.locals.JOYAXISMOTION:
            index = "Input.AXIS-%d" % e.axis 
            try:
                if (self.inputMap[index]["type"] == "Input.AXIS"):
                    key = self.inputMap[index]["key"]
                    axisvalue = self.j.get_axis(e.axis)
                    # All axis are in the range [-a,+a]
                    axisvalue = axisvalue * self.inputMap[index]["scale"]
                    # The value is now in the correct direction and in the range [-1,1]
                    self.data[key] = axisvalue
            except Exception:
                # Axis not mapped, ignore..
                pass          

          if e.type == pygame.locals.JOYBUTTONDOWN:
            index = "Input.BUTTON-%d" % e.button 
            try:
                if (self.inputMap[index]["type"] == "Input.BUTTON"):
                    key = self.inputMap[index]["key"]
                    if (key == "estop"):
                        self.data["estop"] = not self.data["estop"]
                    elif (key == "exit"):
                        self.data["exit"] = not self.data["exit"]
                        logger.info("Toggling AI %d", self.data["exit"])
                    elif (key == "althold"):
                        self.data["althold"] = not self.data["althold"]
                        logger.info("Toggling althold %d", self.data["althold"])
                    else: # Generic cal for pitch/roll
                        self.data[key] = self.inputMap[index]["scale"]
            except Exception:
                # Button not mapped, ignore..
                pass

        # Second if AI is enabled overwrite selected data with AI
        # ----------------------------------------------------------
        if self.data["exit"]:
            self.augmentInputWithAi()

        # Return control Data
        return self.data


    def augmentInputWithAi(self):
        """
        Overrides the throttle input with a controlled takeoff, hover, and land loop.
        You will to adjust the tuning vaiables according to your crazyflie.  
        The max thrust has been set to 0.3 and likely will not fly.  
        I have found that a value  of 0.5 will reach about 1ft off the ground 
        depending on the battery's charge.
        """

        # Keep track of time
        currentTime = time.time()
        timeSinceLastAi = currentTime - self.lastTime
        self.timer1 = self.timer1 + timeSinceLastAi
        self.lastTime = currentTime
        
        # Basic AutoPilot steadly increase thrust, hover, land and repeat
        # -------------------------------------------------------------
        # delay before takeoff 
        if self.timer1 < 0:
            self.aiData["thrust"] = 0
            self.aiData["althold"] = False
            self.aiData["yaw"] = 0
        # takeoff
        elif self.timer1 < self.takeoffTime:
            self.aiData["althold"] = True
            self.aiData["thrust"] = 1
            self.aiData["yaw"] = 0
            #self.aiData["thrust"] = (self.maxThrust/self.takeoffTime) * self.timer1
        # hold
        elif self.timer1 < self.takeoffTime + self.hoverTime:
            self.aiData["althold"] = True
            self.aiData["thrust"] = 0
            self.aiData["yaw"] = 0.5
            #self.aiData["thrust"] = self.maxThrust
        # land
        elif self.timer1 < self.takeoffTime + self.hoverTime + self.landTime:
            self.aiData["althold"] = True
            self.aiData["thrust"] = -1
            self.aiData["yaw"] = 0
            # self.aiData["thrust"] = self.maxThrust - ((self.maxThrust - self.minLandThrust)/self.landTime) * (self.timer1 - (self.takeoffTime + self.hoverTime))
        # repeat
        else:
            self.timer1 = -self.repeatDelay
            self.aiData["thrust"] = 0
            self.aiData["althold"] = False
            self.aiData["yaw"] = 0

        # Override thrust
        self.data["thrust"] = self.aiData["thrust"]

        # override Other inputs as needed
        # --------------------------------------------------------------
        # self.data["roll"] = self.aiData["roll"]
        # self.data["pitch"] = self.aiData["pitch"]
        self.data["yaw"] = self.aiData["yaw"]
        self.data["althold"] = self.aiData["althold"]
        # self.data["pitchcal"] = self.aiData["pitchcal"]
        # self.data["rollcal"] = self.aiData["rollcal"]
        # self.data["estop"] = self.aiData["estop"]
        # self.data["exit"] = self.aiData["exit"]

    # update via param.py -> radiodriver.py -> crazyradio.py -> usbRadio )))
    def updateCrazyFlieParam(self, completename ):
        self.cf.param.set_value( unicode(completename), str(self.cfParams[completename]) )


    def enableRawReading(self, deviceId):
        """Enable reading of raw values (without mapping)"""
        self.j = pygame.joystick.Joystick(deviceId)
        self.j.init()

    def disableRawReading(self):
        """Disable raw reading"""
        # No need to de-init since there's no good support for multiple input devices
        pass

    def readRawValues(self):
        """Read out the raw values from the device"""
        rawaxis = {}
        rawbutton = {}

        for e in pygame.event.get():
            if e.type == pygame.locals.JOYBUTTONDOWN:
                rawbutton[e.button] = 1
            if e.type == pygame.locals.JOYBUTTONUP:
                rawbutton[e.button] = 0
            if e.type == pygame.locals.JOYAXISMOTION:
                rawaxis[e.axis] = self.j.get_axis(e.axis)

        return [rawaxis,rawbutton]

    def getAvailableDevices(self):
        """List all the available devices."""
        dev = []
        pygame.joystick.quit()
        pygame.joystick.init()
        nbrOfInputs = pygame.joystick.get_count()
        for i in range(0,nbrOfInputs):
            j = pygame.joystick.Joystick(i)
            dev.append({"id":i, "name" : j.get_name()})
        return dev

