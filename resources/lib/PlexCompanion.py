# -*- coding: utf-8 -*-
import threading
import traceback
import socket
import Queue

import xbmc

import utils
from plexbmchelper import listener, plexgdm, subscribers, functions, \
    httppersist, settings
from PlexFunctions import ParseContainerKey, GetPlayQueue, \
    ConvertPlexToKodiTime
import playlist
import player


@utils.logging
@utils.ThreadMethodsAdditionalSuspend('plex_serverStatus')
@utils.ThreadMethods
class PlexCompanion(threading.Thread):
    """
    Initialize with a Queue for callbacks
    """
    def __init__(self):
        self.logMsg("----===## Starting PlexCompanion ##===----", 1)
        self.settings = settings.getSettings()

        # Start GDM for server/client discovery
        self.client = plexgdm.plexgdm()
        self.client.clientDetails(self.settings)
        self.logMsg("Registration string is: %s "
                    % self.client.getClientDetails(), 2)

        # Initialize playlist/queue stuff
        self.queueId = None
        self.playlist = None

        # kodi player instance
        self.player = player.Player()

        threading.Thread.__init__(self)

    def _getStartItem(self, string):
        """
        Grabs the Plex id from e.g. '/library/metadata/12987'

        and returns the tuple (typus, id) where typus is either 'queueId' or
        'plexId' and id is the corresponding id as a string
        """
        typus = 'plexId'
        if string.startswith('/library/metadata'):
            try:
                string = string.split('/')[3]
            except IndexError:
                string = ''
        else:
            self.logMsg('Unknown string! %s' % string, -1)
        return typus, string

    def processTasks(self, task):
        """
        Processes tasks picked up e.g. by Companion listener

        task = {
            'action':       'playlist'
            'data':         as received from Plex companion
        }
        """
        self.logMsg('Processing: %s' % task, 2)
        data = task['data']

        if task['action'] == 'playlist':
            try:
                _, queueId, query = ParseContainerKey(data['containerKey'])
            except Exception as e:
                self.logMsg('Exception while processing: %s' % e, -1)
                import traceback
                self.logMsg("Traceback:\n%s" % traceback.format_exc(), -1)
                return
            if self.playlist is not None:
                if self.playlist.typus != data.get('type'):
                    self.logMsg('Switching to Kodi playlist of type %s'
                                % data.get('type'), 1)
                    self.playlist = None
                    self.queueId = None
            if self.playlist is None:
                if data.get('type') == 'music':
                    self.playlist = playlist.Playlist('music',
                                                      player=self.player)
                elif data.get('type') == 'video':
                    self.playlist = playlist.Playlist('video',
                                                      player=self.player)
                else:
                    self.playlist = playlist.Playlist(player=self.player)
            if queueId != self.queueId:
                self.logMsg('New playlist received, updating!', 1)
                self.queueId = queueId
                xml = GetPlayQueue(queueId)
                if xml in (None, 401):
                    self.logMsg('Could not download Plex playlist.', -1)
                    return
                # Clear existing playlist on the Kodi side
                self.playlist.clear()
                items = []
                for item in xml:
                    items.append({
                        'queueId': item.get('playQueueItemID'),
                        'plexId': item.get('ratingKey'),
                        'kodiId': None
                    })
                self.playlist.playAll(
                    items,
                    startitem=self._getStartItem(data.get('key', '')),
                    offset=ConvertPlexToKodiTime(data.get('offset', 0)))
            else:
                self.logMsg('This has never happened before!', -1)

    def run(self):
        httpd = False
        # Cache for quicker while loops
        log = self.logMsg
        client = self.client
        threadStopped = self.threadStopped
        threadSuspended = self.threadSuspended

        # Start up instances
        requestMgr = httppersist.RequestMgr()
        jsonClass = functions.jsonClass(requestMgr, self.settings)
        subscriptionManager = subscribers.SubscriptionManager(
            jsonClass, requestMgr, self.player)

        queue = Queue.Queue(maxsize=100)

        if utils.settings('plexCompanion') == 'true':
            self.logMsg('User activated Plex Companion', 0)
            # Start up httpd
            start_count = 0
            while True:
                try:
                    httpd = listener.ThreadedHTTPServer(
                        client,
                        subscriptionManager,
                        jsonClass,
                        self.settings,
                        queue,
                        ('', self.settings['myport']),
                        listener.MyHandler)
                    httpd.timeout = 0.95
                    break
                except:
                    log("Unable to start PlexCompanion. Traceback:", -1)
                    log(traceback.print_exc(), -1)

                xbmc.sleep(3000)

                if start_count == 3:
                    log("Error: Unable to start web helper.", -1)
                    httpd = False
                    break

                start_count += 1
        else:
            self.logMsg('User deactivated Plex Companion', 0)

        client.start_all()

        message_count = 0
        while not threadStopped():
            # If we are not authorized, sleep
            # Otherwise, we trigger a download which leads to a
            # re-authorizations
            while threadSuspended():
                if threadStopped():
                    break
                xbmc.sleep(1000)
            try:
                if httpd:
                    httpd.handle_request()
                    message_count += 1

                    if message_count > 100:
                        if client.check_client_registration():
                            log("Client is still registered", 1)
                        else:
                            log("Client is no longer registered", 1)
                            log("Plex Companion still running on port %s"
                                % self.settings['myport'], 1)
                        message_count = 0

                # Get and set servers
                subscriptionManager.serverlist = client.getServerList()

                subscriptionManager.notify()
            except:
                log("Error in loop, continuing anyway. Traceback:", 1)
                log(traceback.format_exc(), 1)
            # See if there's anything we need to process
            try:
                task = queue.get(block=False)
            except Queue.Empty:
                pass
            else:
                # Got instructions, process them
                self.processTasks(task)
                queue.task_done()
            xbmc.sleep(10)

        client.stop_all()
        if httpd:
            try:
                httpd.socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            finally:
                httpd.socket.close()
        log("----===## Plex Companion stopped ##===----", 0)
