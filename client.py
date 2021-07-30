
import asyncio
import logging
from getpass import getpass

import slixmpp
from slixmpp.exceptions import IqError, IqTimeout
from argparse import ArgumentParser

class UserClient(slixmpp.ClientXMPP):
    
    def __init__(self, jid, password):
        super().__init__(jid, password)

        self.add_event_handler("session_start", self.start)
        self.add_event_handler("change_status", self.wait_for_presences)
        self.add_event_handler("message", self.message)

        self.received = set()
        self.presences_received = asyncio.Event()

    async def start(self,event):
        try:
            await self.get_roster()
        except IqError as err:
            print('Error: %s' %err.iq['error']['condition'])
        except IqTimeout:
            print('Error: Request timed out')
        self.send_presence()
        
        print('Waiting for presence updates...\n')
        await asyncio.sleep(10)

        await self.show_roster()  
        
        self.handle_user_input()
        
        self.disconnect()
    
    async def show_roster(self):
        print('Roster for %s' % self.boundjid.bare)
        groups = self.client_roster.groups()
        for group in groups:
            print('\n%s' % group)
            print('-' * 72)
            for jid in groups[group]:
                sub = self.client_roster[jid]['subscription']
                name = self.client_roster[jid]['name']
                if self.client_roster[jid]['name']:
                    print(' %s (%s) [%s]' % (name, jid, sub))
                else:
                    print(' %s [%s]' % (jid, sub))

    def message(self,msg):
        if msg['type'] in ('chat', 'normal'):
            print(msg)

    def wait_for_presences(self, pres):
        self.received.add(pres['from'].bare)
        if len(self.received) >= len(self.client_roster.keys()):
            self.presences_received.set()
        else:
            self.presences_received.clear()

    def handle_user_input(self):
        while(True):
            user_input = input('-> ')
            message_length = len(user_input)
            words = user_input.split(" ")
            first_word = words[0]
            print(first_word)
            if first_word[0] == "@":
                recipient_lenght = len(first_word)
                recipient = first_word[1:recipient_lenght] + "@alumchat.xyz"
                body = user_input[recipient_lenght:message_length]
                print(recipient, body)
                self.send_message(mto=recipient, mbody=body, mtype='chat')
            elif first_word == '/quit':
                print("bye")
                break
                

if __name__ =='__main__':
    parser = ArgumentParser(description=UserClient.__doc__)

    parser.add_argument("-j", dest="jid")
    parser.add_argument("-p", dest="password")

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s %(message)s')

    if args.jid is None:
        args.jid = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")
    
    xmpp = UserClient(args.jid, args.password)


    xmpp.connect(address=('alumchat.xyz',5223))
    xmpp.process(forever=False)