import ConfigParser
from datetime import datetime
import re
import smtplib
from email.mime.text import MIMEText

from client import PFCClient
import lxml.html

__author__ = 'cseebach'

class Log(list):
    """
    A simple list subclass which also keeps track of a date and a subject.
    """

    def __init__(self, seq=(), date=datetime.utcnow()):
        super(Log, self).__init__(seq)
        self.date = date
        self.subject = "Chat Log"

class BeerLoggerBot(PFCClient):
    """
    An extension of PFCClient that offers the following commands:

    !sendLog [number] email [subject]
        stops collecting the top log on the stack and sends it to the given email
        optionally, sends a log at a different position in the stack
        note: logs start when this bot logs in, and do not reach backwards into
        the cache

    !viewLogs
        view all the logs in the stack with their numbers and subjects

    !clearLog number
        remove the log with the specified number from the log stack

    !gimmeBeer [kind]
        give the person who sends this command a beer of the specified kind
    """

    def __init__(self, config):
        PFCClient.__init__(self)
        self.config = config
        self.logs = [Log()]

    def start(self):
        """
        Shorthand for the series of commands you'd normally use to start a
        PFCClient
        """
        self.connect(self.config.get("chat", "chat_url"),
                     self.config.get("chat", "name"))
        self.schedule_update()
        self.run()

    @PFCClient.all_fields_responder
    def gimmeBeer(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
                  msg_type, msg_content):
        """
        The !gimmeBeer command.
        """
        splits = msg_content.split()
        if len(splits) == 1:
            self.send("Here's a beer for ya, {}!".format(msg_sender))
        elif len(splits) > 1:
            self.send("Here's a {} for ya, {}!".format(splits[1], msg_sender))

    def make_log_email(self, log_num, subject, to):
        """
        Create a log email message from the given log.
        """
        full_log = "\r\n".join("{} <{}> {}".format(*msg[1:]) for msg in self.logs[log_num])
        msg = MIMEText(full_log)
        msg["Subject"] = "Chat Log: " + subject
        msg["From"] = self.config.get("email", "fromaddr")
        msg["To"] = to

        return msg

    @PFCClient.content_responder
    def sendLog(self, msg_content):
        """
        The !sendLog command
        """
        splits = msg_content.split()
        #arguments must be the command itself and an address, at least
        if len(splits) <=2:
            return

        subject = None
        log_num = 0
        #test if format is !sendLog log_num email
        try:
            log_num = int(splits[1])
            to_addr = splits[2]
        except ValueError:
            #format must be !sendLog email or !sendLog email subject
            to_addr = splits[1]
            if len(splits) > 2:
                subject = " ".join(splits[2:])
        log_num -= 1

        # if subject is specified, change the subject of the log
        # otherwise, use the subject from the log
        if subject:
            self.logs[log_num].subject = subject
        else:
            subject = self.logs[log_num].subject
        message = self.make_log_email(log_num, subject, to_addr).as_string()

        #email sending machinery
        server = smtplib.SMTP(self.config.get("email", "server"))
        server.starttls()
        server.login(self.config.get("email", "username"),
                     self.config.get("email", "password"))
        try:
            server.sendmail(self.config.get("email", "fromaddr"),
                            to_addr, message)
            self.send("Log emailed to "+to_addr)
            if log_num == -1:
                self.logs.append(Log())
        except smtplib.SMTPException:
            self.send("Couldn't send to that email address, sorry.")

    @PFCClient.content_responder
    def viewLogs(self, msg):
        """
        The !viewLogs command.
        """
        for i, log in enumerate(reversed(self.logs)):
            self.send("Log {}: {}".format(-i, log.subject))

    @PFCClient.content_responder
    def clearLog(self, msg_content):
        """
        The !clearLog command.
        """
        splits = msg_content.split()
        if len(splits) < 2:
            return
        try:
            log_num = int(splits[1])
            del self.logs[log_num-1]
            self.send("Log {} cleared.".format(log_num))
        except ValueError:
            self.send("That's not a valid number. :P")
        except IndexError:
            self.send("No log with that number exists.")

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        """
        Need to override this method in order to properly log incoming
        messages.
        """
        self.logs[-1].append([msg_date, msg_time, msg_sender, msg_content])
        PFCClient.message_received(self, msg_number, msg_date, msg_time,
                                   msg_sender, msg_room, msg_type, msg_content)

config = ConfigParser.ConfigParser()
config.read("robot.cfg")

bot = BeerLoggerBot(config)
bot.start()