#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ast
import lxml.html
import re
import requests
import sched
import traceback
import time
import urllib

#Forked from: https://github.com/spirulence/phpfreechatlogger

__author__ = 'Cameron'

def unescape(text):
    return lxml.html.fromstring(text).text_content()

class PFCClientError(Exception):
    pass

class PFCClient(sched.scheduler):
    """
    A basic client class that connects to PHP Free Chat and can recieve and
    send messages
    """

    new_msgs_re = re.compile(r"pfc.handleResponse\('getnewmsg', 'ok', (.*)\);")
    all_fields_responders = {}
    content_responders = {}

    @classmethod
    def all_fields_responder(cls, responder):
        """
        A decorator for responders that need access to all the attributes of
        the message recieved.
        """
        cls.all_fields_responders[responder.__name__] = responder
        return responder

    @classmethod
    def content_responder(cls, responder):
        """
        A decorator for responders that need only the message content.
        """
        cls.content_responders[responder.__name__] = responder
        return responder

    def __init__(self):
        sched.scheduler.__init__(self, time.time, time.sleep)

    def connect(self, chat_url, name):
        """
        Establish a connection to the PHP Free Chat running at the specified URL.
        Connect with the given name.
        """

        self.chat_url = chat_url
        r = requests.get(chat_url)
        if not r:
            raise PFCClientError, "could not get a response at {0}".format(chat_url)

        self.cookies = r.cookies
        if "PHPSESSID" not in self.cookies:
            raise PFCClientError, "was not assigned a PHP session ID"

        client_id = re.search(r'var pfc_clientid\s*?= "(\w*)";', r.text)
        if not client_id:
            raise PFCClientError, "could not obtain a client ID"
        self.client_id = client_id.group(1)

        load_chat_params = {"f":"loadChat", "pfc_ajax":1}
        load_chat = requests.get(chat_url, params=load_chat_params,
                                 cookies=self.cookies)

        data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
                "cmd":'/connect {0} 0 "{1}"'.format(self.client_id, name)}
        try:
            room_request = requests.post(chat_url, data=data, cookies=self.cookies)
            self.room_id = re.search(r"'join', 'ok', Array\('([a-z0-9]*)", room_request.text).group(1)
        except AttributeError:
            raise PFCClientError, "could not get a room ID"

    def schedule_update(self):
        """
        Schedule an update.
        """
        self.enter(3, 0, self.update, [])

    def update(self):
        """
        Update the bot and schedule another update.
        """
        self.schedule_update()

        try:
            update_data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
                           "cmd":'/update {0} {1}'.format(self.client_id, self.room_id)}
            update_request = requests.post(self.chat_url, data=update_data,
                                           cookies=self.cookies)
            self.update_received(update_request.text)
        except requests.RequestException:
            print "Exception while updating from the server."
            traceback.print_exc()
            pass #we'll try again on the next update

    def update_received(self, update_content):
        """
        Called when an update has been recieved from the server.
        """
        for line in update_content.splitlines():
            new_msgs = re.match(self.new_msgs_re, line)
            if new_msgs:
                for new_msg in ast.literal_eval(new_msgs.group(1)):
                    new_msg[-3] = unescape(new_msg[-3])
                    self.message_received(*new_msg[:-2])

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        """
        Called when a message has been recieved from the server.
        """
        try:
            print msg_number, msg_date, msg_time, msg_sender, msg_room, msg_type, msg_content.encode('utf-8')
            if msg_content.startswith("!"):
                command = msg_content[1:].split()[0].lower()
                if command in self.all_fields_responders:
                    responder = self.all_fields_responders[command]
                    responder(self, msg_number, msg_date, msg_time, msg_sender,
                              msg_room, msg_type, msg_content)
                if command in self.content_responders:
                    responder = self.content_responders[command]
                    responder(self, msg_content)
        except:
            print "Exception while responding to a message."
            traceback.print_exc()

    def send(self, msg):
        """
        Send a message to the server.
        """
        try:
            send_data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
                         "cmd":"/send {0} {1} {2}".format(self.client_id, self.room_id, msg)}
            send_request = requests.post(self.chat_url, data=send_data,
                                         cookies=self.cookies)
            self.update_received(send_request.text)
        except requests.RequestException:
            print "Exception while trying to send a message."
            traceback.print_exc()
            self.enter(1, 0, self.send, [msg]) #try again in 1 second
