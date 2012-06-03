import ConfigParser
import re
import smtplib
from email.mime.text import MIMEText
import sqlite3
import time
from datetime import datetime

from dateutil.parser import parse as timeparse
from pfcclient import PFCClient

__author__ = 'cseebach'

def is_email(string):
    return re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}$", string)

class BeerLoggerBot(PFCClient):
    """
    An extension of PFCClient that offers the following commands:

    !gimmeBeer [kind]
        give the person who sends this command a beer of the specified kind

    !gimme [thing]
        give the person who sends this command the given thing

    !markLog start_time [end_time] subject
        name a portion of the log

    !sendLog mark_name [email]
        send a marked portion of the log to the given email. Default to a
        configured mailing list address.
    """

    def __init__(self, config):
        """
        Create a new BeerLoggerBot.
        """
        PFCClient.__init__(self)
        self.config = config
        self.log = sqlite3.connect("log.db")
        self.log_marks = {}
        self.create_log_tables()

    def create_log_tables(self):
        self.log.executescript("""
        CREATE TABLE IF NOT EXISTS log (date float, sender text, content text);
        CREATE INDEX IF NOT EXISTS log_time ON log (date ASC);

        CREATE TABLE IF NOT EXISTS marks (name text PRIMARY KEY, start float, end float);
        """)

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
            self.send("Here's a beer for ya, {0}!".format(msg_sender))
        elif len(splits) > 1:
            if splits[1][0] in "AEIOUaeiou":
                msg = "Here's an {0} for ya, {1}!"
            else:
                msg = "Here's a {0} for ya, {1}!"
            self.send(msg.format(" ".join(splits[1:]), msg_sender))

    @PFCClient.all_fields_responder
    def gimme(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
              msg_type, msg_content):
        """
        The !gimme command.
        """
        splits = msg_content.split()
        if len(splits) == 1:
            self.send("Here's a cool thingy for ya, {0}!".format(msg_sender))
        elif len(splits) == 2:
            thing = msg_content[len("!gimme "):]
            if thing[0] in "AEIOUaeiou":
                msg = "Here's an {0} for ya, {1}!"
            else:
                msg = "Here's a {0} for ya, {1}!"
            self.send(msg.format(" ".join(splits[1:]), msg_sender))
        else:
            thing = msg_content[len("!gimme "):]
            self.send("Here's {0} for ya, {1}!".format(thing, msg_sender))

    @PFCClient.content_responder
    def markLog(self, msg_content):
        """
        The !markLog command

        Give a section of the log a name so that it can be sent and manipulated
        later.
        """
        splits = msg_content.split()

        if len(splits) >= 3:
            max_time_row = self.log.execute("SELECT MAX(date) FROM log;").fetchone()
            if not max_time_row:
                self.send("Nothing logged. Cannot mark.")
                return
            default = datetime.fromtimestamp(max_time_row[0])

            try:
                start_time = time.mktime(timeparse(splits[1], default=default).timetuple())
            except ValueError:
                self.send("Incorrect date format. Cannot mark.")
                return
            try:
                end_time = time.mktime(timeparse(splits[2], default=default).timetuple())
                subject = " ".join(splits[3:])
                self.set_mark(subject, start_time, end_time)
            except ValueError:
                #the end time we tried to parse was actually part of the subject
                end_time = max_time_row[0]
                subject = " ".join(splits[2:])
                self.set_mark(subject, start_time, end_time)
            except IndexError:
                #the subject we tried to get doesn't actually exist
                self.send("No subject specified. Cannot mark.")
        else:
            #give usage help
            self.send("usage: !markLog start_time [end_time] subject")
            self.send("end time defaults to last logged message")
            self.send("specify time like this: DD-MM-YYYY_HH:MM:SS")
            self.send("date defaults to date of last logged message")

    def set_mark(self, subject, start_time, end_time):
        """
        Store a mark in the database.
        """
        self.log.execute("INSERT OR REPLACE INTO marks values (?,?,?)", (subject, start_time, end_time))
        self.log.commit()
        self.send("Mark %s set." % subject)

    @PFCClient.content_responder
    def sendLog(self, msg_content):
        """
        The !sendLog command.

        Email somebody a portion of the log referred to by a given mark. Default
        to the mailing list address.
        """

        splits = msg_content.split()

        if len(splits) == 2:
            subject = splits[1]
            email = self.config.get("mailing_list", "address")
            if self.mark_exists(subject):
                self.send_log_email(subject, email)
            else:
                self.send("No mark by that name.")
        elif len(splits) >= 3:
            if is_email(splits[-1]):
                email = splits[-1]
                subject = " ".join(splits[1:-1])
            else:
                email = self.config.get("mailing_list", "address")
                subject = " ".join(splits[1:])
            if self.mark_exists(subject):
                self.send_log_email(subject, email)
            else:
                self.send("No mark by that name.")
        else:
            #give usage help
            self.send("usage: !sendLog subject [email]")
            self.send("email defaults to configured mailing list address")

    def mark_exists(self, subject):
        results = self.log.execute("SELECT * FROM marks WHERE name=?", (subject,))
        return results.fetchone()

    def make_log_email(self, text, subject, to):
        """
        Create a log email message from the given log text.
        """
        msg = MIMEText(text)
        msg["Subject"] = "Chat Log: " + subject
        msg["From"] = self.config.get("email", "fromaddr")
        msg["To"] = to

        return msg

    def send_log_email(self, subject, to_addr):
        mark = self.log.execute("SELECT * FROM marks WHERE name=?", (subject,)).fetchone()

        messages = []
        for row in self.log.execute("SELECT * FROM log WHERE date >= ? AND date <= ?", (mark[1], mark[2])):
            messages.append("<{0}> {1}".format(row[1], row[2]))

        log_email = self.make_log_email("\n".join(messages), subject, to_addr)

        #email sending machinery
        server = smtplib.SMTP(self.config.get("email", "server"))
        server.starttls()
        server.login(self.config.get("email", "username"),
                     self.config.get("email", "password"))
        try:
            server.sendmail(self.config.get("email", "fromaddr"), to_addr, log_email.as_string())
            self.send("Log emailed to "+to_addr)
        except smtplib.SMTPException:
            self.send("Couldn't send to that email address, sorry.")

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        """
        Need to override this method in order to properly log incoming
        messages.
        """
        self.log_message(msg_date, msg_time, msg_sender, msg_content)
        PFCClient.message_received(self, msg_number, msg_date, msg_time,
                                   msg_sender, msg_room, msg_type, msg_content)

    def log_message(self, msg_date, msg_time, msg_sender, msg_content):
        """
        Put this message in a log.
        """
        parsed_time = datetime.strptime(msg_date+" "+msg_time, "%d\\/%m\\/%Y %H:%M:%S")
        timestamp = time.mktime(parsed_time.timetuple())
        self.log.execute("INSERT INTO log VALUES (?,?,?)", (timestamp, msg_sender, msg_content))
        self.log.commit()

config = ConfigParser.ConfigParser()
config.read("robot.cfg")

bot = BeerLoggerBot(config)
bot.start()
