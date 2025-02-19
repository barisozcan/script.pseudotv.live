#   Copyright (C) 2013 Lunatixz
#
#
# This file is part of PseudoTV.
#
# PseudoTV is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PseudoTV is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PseudoTV.  If not, see <http://www.gnu.org/licenses/>.

import xbmc, xbmcgui, xbmcaddon, xbmcvfs
import subprocess, os, sys, re
import time, threading, datetime, traceback
import urllib, urllib2
import ChannelList

from Playlist import Playlist
from Globals import *
from Channel import Channel
from ChannelList import ChannelList
from FileAccess import FileLock, FileAccess
from xml.etree import ElementTree as ET
from Artdownloader import *
from PVRdownload import *

try:
    from PIL import Image
    from PIL import ImageEnhance
    ImageEnhance = True
except:
    ImageEnhance = False
    pass

    
class EPGWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.focusRow = 0
        self.focusIndex = 0
        self.focusTime = 0
        self.focusEndTime = 0
        self.shownTime = 0
        self.centerChannel = 0
        self.rowCount = 6
        self.channelButtons = [None] * self.rowCount
        self.buttonCache = []
        self.buttonCount = 0
        self.actionSemaphore = threading.BoundedSemaphore()
        self.lastActionTime = time.time()
        self.channelLogos = ''
        self.textcolor = "FFFFFFFF"
        self.focusedcolor = "FF7d7d7d"
        self.clockMode = 0
        self.textfont  = "font14"
        self.startup = time.time()
        self.showingInfo = False
        self.infoOffset = 0
        self.infoOffsetV = 0
        self.log('Using EPG Coloring = ' + str(REAL_SETTINGS.getSetting('EPGcolor_enabled')))
        self.textureButtonFocus = MEDIA_LOC + BUTTON_FOCUS
        self.textureButtonNoFocus = MEDIA_LOC + BUTTON_NO_FOCUS
        self.showSeasonEpisode = REAL_SETTINGS.getSetting("ShowSeEp") == "true"
        self.PVRchtype = ''
        self.PVRmediapath = ''
        self.PVRchname = ''
        self.PVRtitle = ''
        self.setArtwork1_Unlocked = False
        self.setArtwork2_Unlocked = False
        self.VideoWindow = False
        self.type1 = ''
        self.type2 = ''
        self.type1EXT = ''
        self.type2EXT = ''
        self.ArtLST = []

        for i in range(self.rowCount):
            self.channelButtons[i] = []
            
        self.clockMode = ADDON_SETTINGS.getSetting("ClockMode")
        self.toRemove = []


    def onFocus(self, controlid):
        pass


    # set the time labels
    def setTimeLabels(self, thetime):
        self.log('setTimeLabels')
        now = datetime.datetime.fromtimestamp(thetime)
        self.getControl(104).setLabel(now.strftime('%A, %b %d'))
        delta = datetime.timedelta(minutes=30)

        for i in range(3):
            if self.clockMode == "0":
                self.getControl(101 + i).setLabel(now.strftime("%I:%M%p").lower())
            else:
                self.getControl(101 + i).setLabel(now.strftime("%H:%M"))

            now = now + delta

        self.log('setTimeLabels return')


    def log(self, msg, level = xbmc.LOGDEBUG):
        log('EPGWindow: ' + msg, level)

    
    def logDebug(self, msg, level = xbmc.LOGDEBUG):
        if REAL_SETTINGS.getSetting('enable_Debug') == "true":
            log('EPGWindow: ' + msg, level)
                
    
    def onInit(self):
        self.log('onInit')

        timex, timey = self.getControl(120).getPosition()
        timew = self.getControl(120).getWidth()
        timeh = self.getControl(120).getHeight()
        
        #Set timebar path, else use alt. path
        self.currentTimeBar = xbmcgui.ControlImage(timex, timey, timew, timeh, MEDIA_LOC + TIME_BAR)  
        self.addControl(self.currentTimeBar)
        
        try:
            textcolor = int(self.getControl(100).getLabel(), 16)            

            if textcolor > 0:
                self.textcolor = hex(textcolor)[2:]
                self.logDebug("onInit.Self.textcolor = " + str(self.textcolor))
        except:
            pass
        
        try:
            focusedcolor = int(self.getControl(99).getLabel(), 16)

            if focusedcolor > 0:
                self.focusedcolor = hex(focusedcolor)[2:]
                self.logDebug("onInit.Self.focusedcolor = " + str(self.focusedcolor))
        except:
            pass
        
        try:
            self.textfont = self.getControl(105).getLabel()
        except:
            pass
        
        try:
            if self.setChannelButtons(time.time(), self.MyOverlayWindow.currentChannel) == False:
                self.log('Unable to add channel buttons')
                return

            curtime = time.time()
            self.focusIndex = -1
            basex, basey = self.getControl(113).getPosition()
            baseh = self.getControl(113).getHeight()
            basew = self.getControl(113).getWidth()

            # set the button that corresponds to the currently playing show
            for i in range(len(self.channelButtons[2])):
                left, top = self.channelButtons[2][i].getPosition()
                width = self.channelButtons[2][i].getWidth()
                left = left - basex
                starttime = self.shownTime + (left / (basew / 5400.0))
                endtime = starttime + (width / (basew / 5400.0))

                if curtime >= starttime and curtime <= endtime:
                    self.focusIndex = i
                    self.setFocus(self.channelButtons[2][i])
                    self.focusTime = int(time.time())
                    self.focusEndTime = endtime
                    break

            # If nothing was highlighted, just select the first button
            if self.focusIndex == -1:
                self.focusIndex = 0
                self.setFocus(self.channelButtons[2][0])
                left, top = self.channelButtons[2][0].getPosition()
                width = self.channelButtons[2][0].getWidth()
                left = left - basex
                starttime = self.shownTime + (left / (basew / 5400.0))
                endtime = starttime + (width / (basew / 5400.0))
                self.focusTime = int(starttime + 30)
                self.focusEndTime = endtime
            self.focusRow = 2
            self.setShowInfo()
        except:
            self.log("Unknown EPG Initialization Exception", xbmc.LOGERROR)
            self.log(traceback.format_exc(), xbmc.LOGERROR)
            
            try:
                self.close()
            except:
                self.log("Error closing", xbmc.LOGERROR)

            self.MyOverlayWindow.sleepTimeValue = 1
            self.MyOverlayWindow.startSleepTimer()
            return

        self.log('onInit return')


    # setup all channel buttons for a given time
    def setChannelButtons(self, starttime, curchannel, singlerow = -1):
        self.log('setChannelButtons ' + str(starttime) + ', ' + str(curchannel))
        self.centerChannel = self.MyOverlayWindow.fixChannel(curchannel)
        # This is done twice to guarantee we go back 2 channels.  If the previous 2 channels
        # aren't valid, then doing a fix on curchannel - 2 may result in going back only
        # a single valid channel.
        curchannel = self.MyOverlayWindow.fixChannel(curchannel - 1, False)
        curchannel = self.MyOverlayWindow.fixChannel(curchannel - 1, False)
        starttime = self.roundToHalfHour(int(starttime))
        self.setTimeLabels(starttime)
        self.shownTime = starttime
        basex, basey = self.getControl(111).getPosition()
        basew = self.getControl(111).getWidth()
        tmpx, tmpy =  self.getControl(110 + self.rowCount).getPosition()
        timex, timey = self.getControl(120).getPosition()
        timew = self.getControl(120).getWidth()
        timeh = self.getControl(120).getHeight()
        basecur = curchannel
        self.toRemove.append(self.currentTimeBar)
        myadds = []

        for i in range(self.rowCount):
            if singlerow == -1 or singlerow == i:
                self.setButtons(starttime, basecur, i)
                myadds.extend(self.channelButtons[i])
                
            basecur = self.MyOverlayWindow.fixChannel(basecur + 1)

        basecur = curchannel

        for i in range(self.rowCount):
            self.getControl(301 + i).setLabel(self.MyOverlayWindow.channels[basecur - 1].name)
            basecur = self.MyOverlayWindow.fixChannel(basecur + 1)

        for i in range(self.rowCount): 
            try:
                self.getControl(311 + i).setLabel(str(curchannel))
            except:
                pass

            try:        
                if REAL_SETTINGS.getSetting("EPGTextEnable") == "0":
                    self.getControl(321 + i).setImage(self.channelLogos + self.MyOverlayWindow.channels[curchannel - 1].name + '.png')
                else:
                    self.getControl(321 + i).setImage('')
            except:
                pass

            curchannel = self.MyOverlayWindow.fixChannel(curchannel + 1)

        if time.time() >= starttime and time.time() < starttime + 5400:
            dif = int((starttime + 5400 - time.time()))
            self.currentTimeBar.setPosition(int((basex + basew - 2) - (dif * (basew / 5400.0))), timey)
        else:
            if time.time() < starttime:
                self.currentTimeBar.setPosition(basex + 2, timey)
            else:
                 self.currentTimeBar.setPosition(basex + basew - 2 - timew, timey)

        myadds.append(self.currentTimeBar)

        try:
            self.removeControls(self.toRemove)
        except:
            for cntrl in self.toRemove:
                try:
                    self.removeControl(cntrl)
                except:
                    pass

        try:
            self.addControls(myadds)
            self.toRemove = []
            self.log('setChannelButtons return')
        except:
            xbmc.log('self.addControls(myadds) in use')
            pass


    # round the given time down to the nearest half hour
    def roundToHalfHour(self, thetime):
        n = datetime.datetime.fromtimestamp(thetime)
        delta = datetime.timedelta(minutes=30)

        if n.minute > 29:
            n = n.replace(minute=30, second=0, microsecond=0)
        else:
            n = n.replace(minute=0, second=0, microsecond=0)

        return time.mktime(n.timetuple())


    # create the buttons for the specified channel in the given row
    def setButtons(self, starttime, curchannel, row):
        self.log('setButtons ' + str(starttime) + ", " + str(curchannel) + ", " + str(row))
        
        try:
            curchannel = self.MyOverlayWindow.fixChannel(curchannel)
            basex, basey = self.getControl(111 + row).getPosition()
            baseh = self.getControl(111 + row).getHeight()
            basew = self.getControl(111 + row).getWidth()

            chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(curchannel) + '_type'))
            chname = ascii(self.MyOverlayWindow.channels[curchannel - 1].name)
            self.lastExitTime = (ADDON_SETTINGS.getSetting("LastExitTime"))
            if xbmc.Player().isPlaying() == False:
                self.log('No video is playing, not adding buttons')
                self.closeEPG()
                return False

            # Backup all of the buttons to an array
            self.toRemove.extend(self.channelButtons[row])
            del self.channelButtons[row][:]

            # if the channel is paused, then only 1 button needed

            nowDate = datetime.datetime.now()
            self.logDebug("setbuttonnowtime " + str(nowDate))
            playlistpos = int(xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition())
                        
            if chname == 'PseudoCinema' and self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos) <= 1800:
                self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, self.MyOverlayWindow.channels[curchannel - 1].name, focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, textColor=self.textcolor, focusedColor=self.focusedcolor))

            elif self.MyOverlayWindow.channels[curchannel - 1].isPaused:
                if chname in BYPASS_EPG:
                    self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, self.MyOverlayWindow.channels[curchannel - 1].name, focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, textColor=self.textcolor, focusedColor=self.focusedcolor))
                else:
                    self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, self.MyOverlayWindow.channels[curchannel - 1].getCurrentTitle() + " (paused)", focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, textColor=self.textcolor, focusedColor=self.focusedcolor))

            elif chtype >= 10 and self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos) <= self.MyOverlayWindow.shortItemLength:
                if chname in BYPASS_EPG:
                    self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, self.MyOverlayWindow.channels[curchannel - 1].name, focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, textColor=self.textcolor, focusedColor=self.focusedcolor))
                else:
                    self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, self.MyOverlayWindow.channels[curchannel - 1].name + " (stacked)", focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, textColor=self.textcolor, focusedColor=self.focusedcolor))
            else:
                # Find the show that was running at the given time
                # Use the current time and show offset to calculate it
                # At timedif time, channelShowPosition was playing at channelTimes
                # The only way this isn't true is if the current channel is curchannel since
                # it could have been fast forwarded or rewinded (rewound)?
                if curchannel == self.MyOverlayWindow.currentChannel:
                    
                    #Live TV pull date from the playlist entry
                    if chtype == 8:
                        # playlistpos = int(xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition())
                        #episodetitle is actually the start time of each show that the playlist gets from channellist.py
                        tmpDate = self.MyOverlayWindow.channels[curchannel - 1].getItemtimestamp(playlistpos)
                        self.logDebug("setButtons.setbuttonnowtime2 " + str(tmpDate))
                        
                        try:#sloppy fix, for threading issue with strptime.
                            t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                        except:
                            t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                            pass
                            
                        epochBeginDate = time.mktime(t)
                        #beginDate = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
                        #videotime = (nowDate - beginDate).seconds
                        videotime = time.time() - epochBeginDate
                        reftime = time.time()
                    else:
                        playlistpos = int(xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition())
                        videotime = xbmc.Player().getTime()
                        reftime = time.time()
                   
                else:
                    #Live TV pull date from the playlist entry
                    if chtype == 8:
                        playlistpos = self.MyOverlayWindow.channels[curchannel - 1].playlistPosition
                        #playlistpos = int(xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition())
                        #episodetitle is actually the start time of each show that the playlist gets from channellist.py
                        tmpDate = self.MyOverlayWindow.channels[curchannel - 1].getItemtimestamp(playlistpos)
                        self.logDebug("setButtons.setbuttonnowtime2 " + str(tmpDate))
                        
                        try:#sloppy fix, for threading issue with strptime.
                            t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                        except:
                            t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                            pass
                            
                        epochBeginDate = time.mktime(t)
                        #beginDate = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
                        #videotime = (nowDate - beginDate).seconds
                        #loop to ensure we get the current show in the playlist
                        while epochBeginDate + self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos) <  time.time():
                            epochBeginDate += self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos)
                            playlistpos = self.MyOverlayWindow.channels[curchannel - 1].fixPlaylistIndex(playlistpos + 1)
                        videotime = time.time() - epochBeginDate
                        reftime = time.time()
                       
                    else:
                        playlistpos = self.MyOverlayWindow.channels[curchannel - 1].playlistPosition #everyotherchannel epg
                        videotime = self.MyOverlayWindow.channels[curchannel - 1].showTimeOffset
                        reftime = self.MyOverlayWindow.channels[curchannel - 1].lastAccessTime

                    self.log('videotime  & reftime  + starttime + channel === ' + str(videotime) + ', ' + str(reftime) + ', ' + str(starttime) + ', ' + str(curchannel))

                # normalize reftime to the beginning of the video
                reftime -= videotime

                while reftime > starttime:
                    playlistpos -= 1
                    # No need to check bounds on the playlistpos, the duration function makes sure it is correct
                    reftime -= self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos)

                while reftime + self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos) < starttime:
                    reftime += self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos)
                    playlistpos += 1

                # create a button for each show that runs in the next hour and a half
                endtime = starttime + 5400
                totaltime = 0
                totalloops = 0

                while reftime < endtime and totalloops < 1000:
                    xpos = int(basex + (totaltime * (basew / 5400.0)))
                    tmpdur = self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos)
                    shouldskip = False

                    # this should only happen the first time through this loop
                    # it shows the small portion of the show before the current one
                    if reftime < starttime:
                        tmpdur -= starttime - reftime
                        reftime = starttime

                        if tmpdur < 60 * 3:
                            shouldskip = True

                    if self.MyOverlayWindow.hideShortItems and shouldskip == False:
                    
                        # if chtype >= 10 and chtype != 12 and chtype != 13 and self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos) <= 450:
                            # shouldskip = True
                            # tmpdur = 0              
                        if self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos) < self.MyOverlayWindow.shortItemLength and (chtype <= 7 and chtype != 13):
                            shouldskip = True
                            tmpdur = 0
                        else:
                            nextlen = self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos + 1)
                            prevlen = self.MyOverlayWindow.channels[curchannel - 1].getItemDuration(playlistpos - 1)

                            if nextlen < 60:
                                tmpdur += nextlen / 2

                            if prevlen < 60:
                                tmpdur += prevlen / 2

                    width = int((basew / 5400.0) * tmpdur)

                    if width < 30 and shouldskip == False:
                        width = 30
                        tmpdur = int(30.0 / (basew / 5400.0))

                    if width + xpos > basex + basew:
                        width = basex + basew - xpos

                    if shouldskip == False and width >= 30:
                        chanlist = ChannelList()
                        mylabel = self.MyOverlayWindow.channels[curchannel - 1].getItemTitle(playlistpos)
                        mygenre = self.MyOverlayWindow.channels[curchannel - 1].getItemgenre(playlistpos)
                        myLiveID = self.MyOverlayWindow.channels[curchannel - 1].getItemLiveID(playlistpos)
                        chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(curchannel) + '_type'))
                        type = (chanlist.unpackLiveID(myLiveID))[0]
                        playcount = int((chanlist.unpackLiveID(myLiveID))[4])
                        rating = (chanlist.unpackLiveID(myLiveID))[5]
                        
                        if REAL_SETTINGS.getSetting("EPG.xInfo") == "true":
                        
                            if playcount == 0:
                                New = '(NEW)'
                            else:
                                New = ''
                                
                            if rating != 'NR':
                                Rat = '(' + rating + ')'
                            else:
                                Rat = ''
                                
                            mylabel = (mylabel + ' ' + New + ' ' + Rat).replace('()','')
                            
                        if not FileAccess.exists(EPGGENRE_CACHE_LOC):
                            FileAccess.makedirs(EPGGENRE_CACHE_LOC)
                                
                        if FileAccess.exists(EPGGENRE_LOC):
                            EPGTEXTURE_LOC = EPGGENRE_LOC
                        else:
                            EPGTEXTURE_LOC = DEFAULT_EPGGENRE_LOC
                            
                        def EPGtype(genre):
                            if genre in COLOR_RED_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_RED.png')
                            elif genre in COLOR_GREEN_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_GREEN.png')
                            elif genre in COLOR_mdGREEN_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_mdGREEN.png')
                            elif genre in COLOR_BLUE_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_BLUE.png')
                            elif genre in COLOR_ltBLUE_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_ltBLUE.png')
                            elif genre in COLOR_CYAN_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_CYAN.png')
                            elif genre in COLOR_ltCYAN_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_ltCYAN.png')
                            elif genre in COLOR_PURPLE_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_PURPLE.png')
                            elif genre in COLOR_ltPURPLE_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_ltPURPLE.png')
                            elif genre in COLOR_ORANGE_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_ORANGE.png')
                            elif genre in COLOR_YELLOW_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_YELLOW.png')
                            elif genre in COLOR_GRAY_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_GRAY.png')
                            elif genre in COLOR_ltGRAY_TYPE:
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_ltGRAY.png')
                            else:#Unknown
                                EPGTEXTURE = (EPGTEXTURE_LOC + 'COLOR_ltGRAY.png')
                                
                            return EPGTEXTURE
                            
                        if REAL_SETTINGS.getSetting('EPGcolor_enabled') == '1':
                            if type == 'movie' and REAL_SETTINGS.getSetting('EPGcolor_MovieGenre') == "false":
                                self.textureButtonNoFocus = EPGtype('Movie')
                            else:
                                self.textureButtonNoFocus = EPGtype(str(mygenre))
                                
                        elif REAL_SETTINGS.getSetting('EPGcolor_enabled') == '2':
                            self.textureButtonNoFocus = EPGtype(str(chtype))
                           
                        elif REAL_SETTINGS.getSetting('EPGcolor_enabled') == '3':
                            self.textureButtonNoFocus = EPGtype(str(rating)) 
                            
                        else:   
                            self.textureButtonNoFocus = MEDIA_LOC + BUTTON_NO_FOCUS
                      
                        # textureButtonNoFocusFLEname = os.path.split(self.textureButtonNoFocus)[1]        
                        # textureButtonNoFocusFLEname = os.path.splitext(textureButtonNoFocusFLEname)[0]

                        # ButtonHD = (EPGTEXTURE_LOC + 'HD.png')                                      
                        # print xpos, basey, width, baseh
                        # overlayWidth = 35
                        # overlayHeight = 17
                        # overlayXpos = xpos - overlayHeight
                        # overlayBasey = basey - overlayWidth
                        
                        # if ImageEnhance == True:
                            # print 'ImageEnhance'
                            # Background = Image.open(EPGTEXTURE_LOC + 'BG.png')                
                            # Background = Background.convert("RGBA")
                            
                            # ButtonHD = Image.open(EPGTEXTURE_LOC + 'HD.png')               
                            # ButtonHD = ButtonHD.convert("RGBA")
        
                            # Background = Background.resize((basey,baseh), Image.ANTIALIAS)
                            
                            # Background.paste(ButtonHD, (0, 0), ButtonHD)
                            # Background.save(EPGGENRE_CACHE_LOC + mygenre + "-HD.png")
                            # ButtonHD = (EPGGENRE_CACHE_LOC + mygenre + "-HD.png")
                            
                        #######################################################################
                        # overlay = Image.open(self.textureButtonNoFocus)
                        # background = Image.open(EPGTEXTURE_LOC + 'blank.png')   
                        # mask = Image.open(EPGTEXTURE_LOC + 'HD.png') 
                        # background = background.convert("RGBA")
                        # overlay = overlay.convert("RGBA")
                        # mask = mask.convert("RGBA")
                        # new_img = Image.composite(background, overlay, mask) 
                        # # new_img = Image.blend(background, overlay, 0.5)   
                        # new_img.save(EPGGENRE_CACHE_LOC + mygenre + "-HD.png")
                        # self.textureButtonNoFocus = (EPGGENRE_CACHE_LOC + mygenre + "-HD.png")
                        #########################################################################

                        #########################################################################
                        # background = Image.open(self.textureButtonNoFocusGenre)
                        # foreground = Image.open(self.textureButtonNoFocusHD)
                        # Image.blend(background, foreground, 1.0).save(EPGGENRE_CACHE_LOC + mygenre + "-HD.png")
                        # self.textureButtonNoFocusGenre = (EPGGENRE_CACHE_LOC + mygenre + "-HD.png")
                        # background = Image.open(self.textureButtonNoFocusGenre)
                        # overlay = Image.open(self.textureButtonNoFocusHD)
                        # background = background.convert("RGBA")
                        # overlay = overlay.convert("RGBA")
                        # new_img = Image.blend(background, overlay, 0.5)                                
                        # new_img.save(EPGGENRE_CACHE_LOC + str(chtype) + '-HD.png')
                        # self.textureButtonNoFocusChtype = (EPGGENRE_CACHE_LOC + str(chtype) + '-HD.png')
                        #########################################################################
                             
                        self.channelButtons[row].append(xbmcgui.ControlButton(xpos, basey, width, baseh, mylabel, focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, font=self.textfont, textColor=self.textcolor, focusedColor=self.focusedcolor))
                        # self.channelButtons[row].append(xbmcgui.ControlButton(overlayXpos, overlayBasey, overlayWidth, overlayHeight, '', focusTexture=self.textureButtonFocus, noFocusTexture=ButtonHD, alignment=4, font=self.textfont, textColor=self.textcolor, focusedColor=self.focusedcolor))

                    totaltime += tmpdur
                    reftime += tmpdur
                    playlistpos += 1
                    totalloops += 1

                if totalloops >= 1000:
                    self.log("Broken big loop, too many loops, reftime is " + str(reftime) + ", endtime is " + str(endtime))

                # If there were no buttons added, show some default button
                if len(self.channelButtons[row]) == 0:
                    self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, self.MyOverlayWindow.channels[curchannel - 1].name, focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus, alignment=4, textColor=self.textcolor, focusedColor=self.focusedcolor))
        except:
            self.log("Exception in setButtons", xbmc.LOGERROR)
            self.log(traceback.format_exc(), xbmc.LOGERROR)

        self.log('setButtons return')
        return True


    def onAction(self, act):
        self.log('onAction ' + str(act.getId()))
        
        if self.actionSemaphore.acquire(False) == False:
            self.log('Unable to get semaphore')
            return

        action = act.getId()
        
        try:
            if action in ACTION_PREVIOUS_MENU:
                self.closeEPG()           
                if self.showingInfo:
                    self.infoOffset = 0
                    self.infoOffsetV = 0
            
            elif action == ACTION_MOVE_DOWN: 
                self.GoDown()     
                if self.showingInfo:  
                    self.infoOffsetV -= 1
            
            elif action == ACTION_MOVE_UP:
                self.GoUp()           
                if self.showingInfo: 
                    self.infoOffsetV += 1

            elif action == ACTION_MOVE_LEFT:
                self.GoLeft()           
                if self.showingInfo:
                    self.infoOffset -= 1
            
            elif action == ACTION_MOVE_RIGHT:
                self.GoRight()           
                if self.showingInfo:
                    self.infoOffset += 1
            
            elif action == ACTION_STOP:
                self.closeEPG()           
                if self.showingInfo:
                    self.infoOffset = 0
                    self.infoOffsetV = 0
            
            elif action == ACTION_SELECT_ITEM:
                lastaction = time.time() - self.lastActionTime           
                if self.showingInfo:
                    self.infoOffset = 0
                    self.infoOffsetV = 0

                if lastaction >= 2:
                    self.selectShow()
                    self.closeEPG()
                    self.infoOffset = 0
                    self.infoOffsetV = 0
                    self.lastActionTime = time.time()
            
            elif action == ACTION_MOVE_DOWN: 
                self.GoDown()           
                if self.showingInfo:
                    self.infoOffsetV -= 1
            
            elif action == ACTION_PAGEDOWN: 
                self.GoPgDown()  
                if self.showingInfo:  
                    self.infoOffsetV -= 6       
            
            elif action == ACTION_MOVE_UP:
                self.GoUp()           
                if self.showingInfo:
                    self.infoOffsetV += 1
                    
            elif action == ACTION_PAGEUP:
                self.GoPgUp()           
                if self.showingInfo:
                    self.infoOffsetV += 6
                    
            elif action == ACTION_RECORD:
                self.log('ACTION_RECORD')
                PVRrecord(self.PVRchtype, self.PVRmediapath, self.PVRchname, self.PVRtitle)
        except:
            self.log("Unknown EPG Exception", xbmc.LOGERROR)
            self.log(traceback.format_exc(), xbmc.LOGERROR)

            try:
                self.close()
            except:
                self.log("Error closing", xbmc.LOGERROR)

            self.MyOverlayWindow.sleepTimeValue = 1
            self.MyOverlayWindow.startSleepTimer()
            return

        self.actionSemaphore.release()
        self.log('onAction return')


    def closeEPG(self):
        self.log('closeEPG')

        try:
            self.removeControl(self.currentTimeBar)
            self.MyOverlayWindow.startSleepTimer()
        except:
            pass

        self.close()


    def onControl(self, control):
        self.log('onControl')


    # Run when a show is selected, so close the epg and run the show
    def onClick(self, controlid):
        self.log('onClick')
        try:
            if self.actionSemaphore.acquire(False) == False:
                self.log('Unable to get semaphore')
                return

            lastaction = time.time() - self.lastActionTime

            if lastaction >= 2:
                try:
                    selectedbutton = self.getControl(controlid)
                except:
                    self.actionSemaphore.release()
                    self.log('onClick unknown controlid ' + str(controlid))
                    return

                for i in range(self.rowCount):
                    for x in range(len(self.channelButtons[i])):
                        mycontrol = 0
                        mycontrol = self.channelButtons[i][x]

                        if selectedbutton == mycontrol:
                            self.focusRow = i
                            self.focusIndex = x
                            self.selectShow()
                            self.closeEPG()
                            self.lastActionTime = time.time()
                            self.actionSemaphore.release()
                            self.log('onClick found button return')
                            return

                self.lastActionTime = time.time()
                self.closeEPG()

            self.actionSemaphore.release()
            self.log('onClick return')
        except:
            pass
    
   
    def GoPgDown(self):
        self.log('GoPgDown')
        newchannel = self.centerChannel
        for x in range(0, 6):
            newchannel = self.MyOverlayWindow.fixChannel(newchannel + 1)
        self.setChannelButtons(self.shownTime, self.MyOverlayWindow.fixChannel(newchannel))
        self.setProperButton(0)
        self.log('GoPgDown return')

    
    def GoPgUp(self):
        self.log('GoPgUp')
        newchannel = self.centerChannel
        for x in range(0, 6):
            newchannel = self.MyOverlayWindow.fixChannel(newchannel - 1, False)
        self.setChannelButtons(self.shownTime, self.MyOverlayWindow.fixChannel(newchannel))
        self.setProperButton(0)
        self.log('GoPgUp return')

        
    def GoDown(self):
        self.log('goDown')
        try:
            # change controls to display the proper junks
            if self.focusRow == self.rowCount - 1:
                self.setChannelButtons(self.shownTime, self.MyOverlayWindow.fixChannel(self.centerChannel + 1))
                self.focusRow = self.rowCount - 2

            self.setProperButton(self.focusRow + 1)
            self.log('goDown return')
        except:
            pass

    
    def GoUp(self):
        self.log('goUp')
        try:

            # same as godown
            # change controls to display the proper junks
            if self.focusRow == 0:
                self.setChannelButtons(self.shownTime, self.MyOverlayWindow.fixChannel(self.centerChannel - 1, False))
                self.focusRow = 1

            self.setProperButton(self.focusRow - 1)
            self.log('goUp return')
        except:
            pass

    
    def GoLeft(self):
        self.log('goLeft')
        try:
            basex, basey = self.getControl(111 + self.focusRow).getPosition()
            basew = self.getControl(111 + self.focusRow).getWidth()

            # change controls to display the proper junks
            if self.focusIndex == 0:
                left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
                width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
                left = left - basex
                starttime = self.shownTime + (left / (basew / 5400.0))
                self.setChannelButtons(self.shownTime - 1800, self.centerChannel)
                curbutidx = self.findButtonAtTime(self.focusRow, starttime + 30)

                if(curbutidx - 1) >= 0:
                    self.focusIndex = curbutidx - 1
                else:
                    self.focusIndex = 0
            else:
                self.focusIndex -= 1

            left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
            width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            endtime = starttime + (width / (basew / 5400.0))
            self.setFocus(self.channelButtons[self.focusRow][self.focusIndex])
            self.setShowInfo()
            self.focusEndTime = endtime
            self.focusTime = starttime + 30
            self.log('goLeft return')
        except:
            pass

    
    def GoRight(self):
        self.log('goRight')
        try:
            basex, basey = self.getControl(111 + self.focusRow).getPosition()
            basew = self.getControl(111 + self.focusRow).getWidth()

            # change controls to display the proper junks
            if self.focusIndex == len(self.channelButtons[self.focusRow]) - 1:
                left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
                width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
                left = left - basex
                starttime = self.shownTime + (left / (basew / 5400.0))
                self.setChannelButtons(self.shownTime + 1800, self.centerChannel)
                curbutidx = self.findButtonAtTime(self.focusRow, starttime + 30)

                if(curbutidx + 1) < len(self.channelButtons[self.focusRow]):
                    self.focusIndex = curbutidx + 1
                else:
                    self.focusIndex = len(self.channelButtons[self.focusRow]) - 1
            else:
                self.focusIndex += 1

            left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
            width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            endtime = starttime + (width / (basew / 5400.0))
            self.setFocus(self.channelButtons[self.focusRow][self.focusIndex])
            self.setShowInfo()
            self.focusEndTime = endtime
            self.focusTime = starttime + 30
            self.log('goRight return')
        except:
            pass

    
    def findButtonAtTime(self, row, selectedtime):
        self.log('findButtonAtTime ' + str(row))
        basex, basey = self.getControl(111 + row).getPosition()
        baseh = self.getControl(111 + row).getHeight()
        basew = self.getControl(111 + row).getWidth()

        for i in range(len(self.channelButtons[row])):
            left, top = self.channelButtons[row][i].getPosition()
            width = self.channelButtons[row][i].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            endtime = starttime + (width / (basew / 5400.0))

            if selectedtime >= starttime and selectedtime <= endtime:
                return i

        return -1


    # based on the current focus row and index, find the appropriate button in
    # the new row to set focus to
    def setProperButton(self, newrow, resetfocustime = False):
        self.log('setProperButton ' + str(newrow))
        self.focusRow = newrow
        basex, basey = self.getControl(111 + newrow).getPosition()
        baseh = self.getControl(111 + newrow).getHeight()
        basew = self.getControl(111 + newrow).getWidth()

        for i in range(len(self.channelButtons[newrow])):
            left, top = self.channelButtons[newrow][i].getPosition()
            width = self.channelButtons[newrow][i].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            endtime = starttime + (width / (basew / 5400.0))

            if self.focusTime >= starttime and self.focusTime <= endtime:
                self.focusIndex = i
                self.setFocus(self.channelButtons[newrow][i])
                self.setShowInfo()
                self.focusEndTime = endtime

                if resetfocustime:
                    self.focusTime = starttime + 30

                self.log('setProperButton found button return')
                return

        self.focusIndex = 0
        self.setFocus(self.channelButtons[newrow][0])
        left, top = self.channelButtons[newrow][0].getPosition()
        width = self.channelButtons[newrow][0].getWidth()
        left = left - basex
        starttime = self.shownTime + (left / (basew / 5400.0))
        endtime = starttime + (width / (basew / 5400.0))
        self.focusEndTime = endtime

        if resetfocustime:
            self.focusTime = starttime + 30

        self.setShowInfo()
        self.log('setProperButton return')

        
    def setShowInfo(self):
        self.log('setShowInfo')
        ART_CACHE = False
        self.showingInfo = True
        basex, basey = self.getControl(111 + self.focusRow).getPosition()
        baseh = self.getControl(111 + self.focusRow).getHeight()
        basew = self.getControl(111 + self.focusRow).getWidth()
        # use the selected time to set the video
        left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
        width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
        left = left - basex + (width / 2)
        starttime = self.shownTime + (left / (basew / 5400.0))
        chnoffset = self.focusRow - 2
        newchan = self.centerChannel
        self.Artdownloader = Artdownloader()  
        mpath = ''
        
        while chnoffset != 0:
            if chnoffset > 0:
                newchan = self.MyOverlayWindow.fixChannel(newchan + 1, True)
                chnoffset -= 1
            else:
                newchan = self.MyOverlayWindow.fixChannel(newchan - 1, False)
                chnoffset += 1

        plpos = self.determinePlaylistPosAtTime(starttime, newchan)

        if plpos == -1:
            self.log('Unable to find the proper playlist to set from EPG')
            return

        now = time.time()
        chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(newchan) + '_type'))
        setting3 = ADDON_SETTINGS.getSetting('Channel_' + str(newchan) + '_3')

        mediapath = ascii(self.MyOverlayWindow.channels[newchan - 1].getItemFilename(plpos))
        mediaduration = int((self.MyOverlayWindow.channels[newchan - 1].getItemDuration(plpos)) - now)  
        chname = ascii(self.MyOverlayWindow.channels[newchan - 1].name)
        genre = ascii(self.MyOverlayWindow.channels[newchan - 1].getItemgenre(plpos))
        title = ascii(self.MyOverlayWindow.channels[newchan - 1].getItemTitle(plpos))
        LiveID = ascii(self.MyOverlayWindow.channels[newchan - 1].getItemLiveID(plpos))
        chanlist = ChannelList()
        
        if mediapath[0:5] == 'stack':
            smpath = (mediapath.split(' , ')[0]).replace('stack://','')
            mpath = (os.path.split(smpath)[0])
        else:
            mpath = (os.path.split(mediapath)[0])
                
        self.PVRchtype = chtype
        self.PVRmediapath = mediapath
        self.PVRchname = chname
        self.PVRtitle = title
        
        LiveID = chanlist.unpackLiveID(LiveID)
        type = LiveID[0]
        id = LiveID[1]
        dbid = LiveID[2]
        Managed = LiveID[3]
        playcount = int(LiveID[4])
        rating = LiveID[5]
                
        #Check if VideoWindow Patch found, change label.
        if FileAccess.exists(os.path.join(skinPath, 'custom_script.pseudotv.live_9506.xml')):
            self.VideoWindow = True
            try:
                self.getControl(523).setLabel('NOW WATCHING:')
            except:
                pass
                
        #Change Label when Dynamic artwork enabled
        try:
            if REAL_SETTINGS.getSetting("art.enable") == "true":     
            
                if self.infoOffset > 0:
                    self.getControl(522).setLabel('COMING UP:')
                    self.getControl(515).setVisible(False)
                    
                elif self.infoOffset < 0:
                    self.getControl(522).setLabel('ALREADY SEEN:')
                    self.getControl(515).setVisible(False)
                    
                elif self.infoOffset == 0 and self.infoOffsetV == 0:
                    self.getControl(522).setLabel('NOW WATCHING:')
                    self.getControl(515).setVisible(False)
                    
                elif self.infoOffsetV != 0 and self.infoOffset == 0:
                    self.getControl(522).setLabel('ON NOW:')                  
                    self.getControl(515).setVisible(False)
                                     
            else:       
                self.getControl(522).setLabel('NOW WATCHING:')
                self.getControl(515).setVisible(True)    
        except:
            pass

        SEtitle = self.MyOverlayWindow.channels[newchan - 1].getItemEpisodeTitle(plpos) 
        
        try:
            SEinfo = SEtitle.split(' -')[0]
            season = int(SEinfo.split('x')[0])
            episode = int(SEinfo.split('x')[1])
            eptitles = SEtitle.split('- ')
            eptitle = (eptitles[1] + (' - ' + eptitles[2] if len(eptitles) > 2 else ''))
            
            if self.showSeasonEpisode:
                swtitle = ('S' + ('0' if season < 10 else '') + str(season) + 'E' + ('0' if episode < 10 else '') + str(episode) + ' - ' + (eptitle)).replace('  ',' ')
            else:
                swtitle = SEtitle      
        except:
            swtitle = SEtitle
            pass
            
        self.getControl(500).setLabel((self.MyOverlayWindow.channels[newchan - 1].getItemTitle(plpos)).replace("*NEW*", ""))
        self.getControl(501).setLabel(swtitle)
        self.getControl(502).setLabel(self.MyOverlayWindow.channels[newchan - 1].getItemDescription(plpos))
        self.getControl(503).setImage(self.channelLogos + ascii(self.MyOverlayWindow.channels[newchan - 1].name) + '.png')
        
        if REAL_SETTINGS.getSetting("art.enable") == "true": 
            self.log('Dynamic artwork enabled')
            
            #hide xbmc.videoplayer art since using dynamic art
            try:
                self.getControl(513).setVisible(False)
            except:
                pass  
                
            #Sickbeard/Couchpotato == Managed
            try:
                if Managed == 'True':
                    self.getControl(511).setVisible(True)  
                    if type == 'tvshow':
                        self.getControl(511).setImage(DEFAULT_IMAGES_LOC + 'SB.png')
                    else:
                        self.getControl(511).setImage(DEFAULT_IMAGES_LOC + 'CP.png')                          
                else:
                    self.getControl(511).setVisible(False)  
            except:
                pass     
                
            #Unaired/aired == Playcount 0 = New
            try:
                self.getControl(512).setVisible(True)
                if playcount == 0:
                    self.getControl(512).setImage(MEDIA_LOC + 'NEW.png')
                elif playcount >= 1:
                    self.getControl(512).setImage(MEDIA_LOC + 'OLD.png')      
                else:
                    self.getControl(512).setVisible(False)      
            except:
                pass  

            try:
                type1 = str(self.getControl(507).getLabel())
                type1EXT = self.Artdownloader.EXTtype(type1)
                self.setArtwork1(type, chtype, id, mpath, type1EXT)
                # self.getControl(508).setImage('NA.png')
                # setImage1 = self.Artdownloader.FindArtwork(type, chtype, id, mpath, type1EXT)
                # self.getControl(508).setImage(setImage1)
            except:
                pass
               
            try:
                type2 = str(self.getControl(509).getLabel())
                type2EXT = self.Artdownloader.EXTtype(type2)
                self.setArtwork2(type, chtype, id, mpath, type2EXT)
                # self.getControl(510).setImage('NA.png')
                # setImage2 = self.Artdownloader.FindArtwork(type, chtype, id, mpath, type2EXT)
                # self.getControl(510).setImage(setImage2)
            except:
                pass
        
        else:
            #use xbmc.videoplayer art since not using dynamic art
            try:
                self.getControl(513).setVisible(True)
            except:
                pass   
                
        self.log('setShowInfo return')

        
    def setArtwork1(self, type, chtype, id, mpath, type1EXT):
        self.log('setArtwork1')
        try:
            self.getControl(508).setImage('NA.png')
            setImage1 = self.Artdownloader.FindArtwork_NEW(type, chtype, id, mpath, type1EXT)
            self.getControl(508).setImage(setImage1)
        except:
            pass  
    
    
    def setArtwork2(self, type, chtype, id, mpath, type2EXT):
        self.log('setArtwork2')
        try: 
            self.getControl(510).setImage('NA.png')
            setImage2 = self.Artdownloader.FindArtwork_NEW(type, chtype, id, mpath, type2EXT)
            self.getControl(510).setImage(setImage2)
        except:
            pass
    
        
    # using the currently selected button, play the proper shows
    def selectShow(self):
        self.log('selectShow')    
        CurChannel = self.MyOverlayWindow.currentChannel
        REAL_SETTINGS.setSetting('LastChannel', str(CurChannel))
        
        try:
            basex, basey = self.getControl(111 + self.focusRow).getPosition()
            baseh = self.getControl(111 + self.focusRow).getHeight()
            basew = self.getControl(111 + self.focusRow).getWidth()
            # use the selected time to set the video
            left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
            width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
            left = left - basex + (width / 2)
            starttime = self.shownTime + (left / (basew / 5400.0))
            chnoffset = self.focusRow - 2
            newchan = self.centerChannel
            nowDate = datetime.datetime.now()
            
            while chnoffset != 0:
                if chnoffset > 0:
                    newchan = self.MyOverlayWindow.fixChannel(newchan + 1, True)
                    chnoffset -= 1
                else:
                    newchan = self.MyOverlayWindow.fixChannel(newchan - 1, False)
                    chnoffset += 1

            plpos = self.determinePlaylistPosAtTime(starttime, newchan)
            chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(newchan) + '_type'))
            
            if plpos == -1:
                self.log('Unable to find the proper playlist to set from EPG', xbmc.LOGERROR)
                return
           
            timedif = (time.time() - self.MyOverlayWindow.channels[newchan - 1].lastAccessTime)
            
            pos = self.MyOverlayWindow.channels[newchan - 1].playlistPosition
            
            showoffset = self.MyOverlayWindow.channels[newchan - 1].showTimeOffset

            
            #code added for "LiveTV" types
            #Get the Start time of the show from "episodeitemtitle"
            #we just passed this from channellist.py ; just a fill in to get value
            #Start at the beginning of the playlist get the first epoch date
            #position pos of the playlist convert the string add until we get to the current item in the playlist

            if chtype == 8:
                tmpDate = self.MyOverlayWindow.channels[newchan - 1].getItemtimestamp(pos)
                self.log("selectshow tmpdate " + str(tmpDate))
                
                try:#sloppy fix, for threading issue with strptime.
                    t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                except:
                    t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                    pass
                    
                epochBeginDate = time.mktime(t)
                #beginDate = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
                #loop till we get to the current show  
                while epochBeginDate + self.MyOverlayWindow.channels[newchan - 1].getItemDuration(pos) <  time.time():
                    epochBeginDate += self.MyOverlayWindow.channels[newchan - 1].getItemDuration(pos)
                    pos = self.MyOverlayWindow.channels[newchan - 1].fixPlaylistIndex(pos + 1)
                    self.log('live tv while loop')

            # adjust the show and time offsets to properly position inside the playlist
            else:
                while showoffset + timedif > self.MyOverlayWindow.channels[newchan - 1].getItemDuration(pos):
                    self.log('duration ' + str(self.MyOverlayWindow.channels[newchan - 1].getItemDuration(pos)))
                    timedif -= self.MyOverlayWindow.channels[newchan - 1].getItemDuration(pos) - showoffset
                    pos = self.MyOverlayWindow.channels[newchan - 1].fixPlaylistIndex(pos + 1)
                    showoffset = 0

                self.log('pos + plpos ' + str(pos) +', ' + str(plpos))
            
            if self.MyOverlayWindow.currentChannel == newchan:
                if plpos == xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition():
                    self.log('selectShow return current show')
                    return

                if chtype == 8:
                    self.log('selectShow return current LiveTV channel')
                    return
            
            if pos != plpos:
                if chtype == 8:
                    self.log('selectShow return different LiveTV channel')
                    return
                else:
                    self.MyOverlayWindow.channels[newchan - 1].setShowPosition(plpos)
                    self.MyOverlayWindow.channels[newchan - 1].setShowTime(0)
                    self.MyOverlayWindow.channels[newchan - 1].setAccessTime(time.time())

            self.MyOverlayWindow.newChannel = newchan
            self.log('selectShow return')
        except:
            pass
        
        
    def determinePlaylistPosAtTime(self, starttime, channel):
        self.log('determinePlaylistPosAtTime ' + str(starttime) + ', ' + str(channel))
        channel = self.MyOverlayWindow.fixChannel(channel)

        chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_type'))
        self.lastExitTime = ADDON_SETTINGS.getSetting("LastExitTime")
        nowDate = datetime.datetime.now()
        # if the channel is paused, then it's just the current item
        if self.MyOverlayWindow.channels[channel - 1].isPaused:
            self.log('determinePlaylistPosAtTime paused return')
            return self.MyOverlayWindow.channels[channel - 1].playlistPosition
        else:
            # Find the show that was running at the given time
            # Use the current time and show offset to calculate it
            # At timedif time, channelShowPosition was playing at channelTimes
            # The only way this isn't true is if the current channel is curchannel since
            # it could have been fast forwarded or rewinded (rewound)?
            if channel == self.MyOverlayWindow.currentChannel: #currentchannel epg
                #Live TV pull date from the playlist entry
                if chtype == 8:
                    playlistpos = int(xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition())
                    tmpDate = self.MyOverlayWindow.channels[channel - 1].getItemtimestamp(playlistpos)
                    self.log("setbuttonnowtime2 " + str(tmpDate))
                   
                    try:#sloppy fix, for threading issue with strptime.
                        t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                    except:
                        t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                        pass
                            
                    epochBeginDate = time.mktime(t)
                    videotime = time.time() - epochBeginDate
                    reftime = time.time()
                else:
                    playlistpos = int(xbmc.PlayList(xbmc.PLAYLIST_VIDEO).getposition())
                    try:
                        videotime = xbmc.Player().getTime()
                    except:
                        videotime = xbmc.Player().getTime()
                        pass
                    reftime = time.time()
                   
            else:
                #Live TV pull date from the playlist entry
                if chtype == 8:
                    playlistpos = self.MyOverlayWindow.channels[channel - 1].playlistPosition
                    tmpDate = self.MyOverlayWindow.channels[channel - 1].getItemtimestamp(playlistpos)
                    self.log("setbuttonnowtime2 " + str(tmpDate))
                       
                    try:#sloppy fix, for threading issue with strptime.
                        t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                    except:
                        t = time.strptime(tmpDate, '%Y-%m-%d %H:%M:%S')
                        pass
                        
                    epochBeginDate = time.mktime(t)
                    while epochBeginDate + self.MyOverlayWindow.channels[channel - 1].getItemDuration(playlistpos) <  time.time():
                        epochBeginDate += self.MyOverlayWindow.channels[channel - 1].getItemDuration(playlistpos)
                        playlistpos = self.MyOverlayWindow.channels[channel - 1].fixPlaylistIndex(playlistpos + 1)
                       
                    videotime = time.time() - epochBeginDate
                    self.log('videotime ' + str(videotime))
                    reftime = time.time()
                      
                else:
                    playlistpos = self.MyOverlayWindow.channels[channel - 1].playlistPosition 
                    videotime = self.MyOverlayWindow.channels[channel - 1].showTimeOffset
                    reftime = self.MyOverlayWindow.channels[channel - 1].lastAccessTime

            # normalize reftime to the beginning of the video
            reftime -= videotime

            while reftime > starttime:
                playlistpos -= 1
                reftime -= self.MyOverlayWindow.channels[channel - 1].getItemDuration(playlistpos)

            while reftime + self.MyOverlayWindow.channels[channel - 1].getItemDuration(playlistpos) < starttime:
                reftime += self.MyOverlayWindow.channels[channel - 1].getItemDuration(playlistpos)
                playlistpos += 1

            self.log('determinePlaylistPosAtTime return' + str(self.MyOverlayWindow.channels[channel - 1].fixPlaylistIndex(playlistpos)))
            return self.MyOverlayWindow.channels[channel - 1].fixPlaylistIndex(playlistpos)
