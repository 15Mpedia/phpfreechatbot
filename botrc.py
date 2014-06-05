#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ConfigParser
import datetime
import json
import os
import random
import re
import sys
import threading
import time
import urllib

from pfcclient import PFCClient

#Forked from: https://github.com/spirulence/phpfreechatlogger

__author__ = 'cseebach'

class WikiChatBot(PFCClient):
    """
    An extension of PFCClient that offers the following commands:

    !gimme [thing]
        give the person who sends this command the given thing
    """

    def __init__(self, config):
        """
        Create a new wikichatbot
        """
        PFCClient.__init__(self)
        self.config = config
        self.delay = 60

    def start(self):
        """
        Shorthand for the series of commands you'd normally use to start a
        PFCClient
        """
        self.connect(self.config.get("chat", "chat_url"),
                     self.config.get("chat", "name") + str(random.randint(1000,9999)))
        self.delay = int(self.config.get("chat", "delay"))
        self.schedule_update()
        self.rc = threading.Thread(target=self.recentchanges, args=[])
        self.rc.start()
        self.run()
    
    def recentchanges(self):
        time.sleep(30) #courtesy delay while bot enter to chat
        while True:
            periodtocheck = self.delay #in seconds
            rcend = (datetime.datetime.now() - datetime.timedelta(seconds=periodtocheck)).strftime('%Y%m%d%H%M%S')
            print 'Leyendo cambios recientes desde', rcend
            urlrc = 'http://wiki.15m.cc/w/api.php?action=query&list=recentchanges&rcshow=anon&rcprop=title|ids|user|timestamp&rcend=%s&rclimit=500&format=json' % (rcend)
            jsonrc = json.loads(unicode(urllib.urlopen(urlrc).read(), 'utf-8'))
            for rcedit in jsonrc['query']['recentchanges']:
                diffurl = u'http://wiki.15m.cc/w/index.php?oldid=%s&diff=prev' % (rcedit['revid'])
                msg = u"%s editó \"%s\" a las %s. Ver diff: %s" % (rcedit['user'], rcedit['title'], rcedit['timestamp'], diffurl)
                self.send(msg.encode('utf-8'))
                time.sleep(5)
            
            #break #for testing
            time.sleep(self.delay) #seconds of delay until next iteration
    
if __name__ == "__main__":
    config = ConfigParser.ConfigParser()
    config.read("botrc.cfg")

    bot = WikiChatBot(config)
    bot.start()
