#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ConfigParser
import random
import re
import time
from datetime import datetime
import urllib
import os
import random

from pfcclient import PFCClient

#Forked from: https://github.com/spirulence/phpfreechatlogger

__author__ = 'cseebach'

def is_email(string):
    return re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}$", string)

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

    def start(self):
        """
        Shorthand for the series of commands you'd normally use to start a
        PFCClient
        """
        self.connect(self.config.get("chat", "chat_url"),
                     self.config.get("chat", "name") + str(random.randint(1000,9999)))
        self.schedule_update()
        self.run()

    @PFCClient.content_responder
    def random(self, msg_content):
        text = lxml.html.fromstring(urllib.urlopen("").read()).text_content()
        words = text.split()
        response_words = [random.choice(words) for i in xrange(5)]
        self.send(" ".join(response_words) + ".")

    @PFCClient.all_fields_responder
    def hola(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
              msg_type, msg_content):
        """
        The !hola command
        """
        splits = msg_content.split()
        if len(splits) == 1:
            self.send("Hola {0}!".format(msg_sender))
        elif len(splits) == 2:
            param = msg_content[len("!hola "):]
            self.send("Hola {0}! de parte de {1}".format(param, msg_sender))
        else:
            self.send("Hola!")
    
    @PFCClient.all_fields_responder
    def topsy(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
              msg_type, msg_content):
        """
        The !topsy command for social trends
        http://topsy.com/analytics
        """
        splits = msg_content.strip().split()
        if len(splits) == 1:
            self.send("http://topsy.com/analytics")
        elif len(splits) == 2:
            self.send("http://topsy.com/analytics?q1={0}".format(splits[1]))
        elif len(splits) == 3:
            self.send("http://topsy.com/analytics?q1={0}&q2={1}".format(splits[1], splits[2]))
        else:
            self.send("http://topsy.com/analytics?q1={0}&q2={1}&q3={2}".format(splits[1], splits[2], splits[3]))

if __name__ == "__main__":
    config = ConfigParser.ConfigParser()
    config.read("robot.cfg")

    bot = WikiChatBot(config)
    bot.start()
