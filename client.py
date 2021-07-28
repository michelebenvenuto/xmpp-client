
import logging
from getpass import getpass

import slixmpp
from argparse import ArgumentParser

class UserClient(slixmpp.ClientXMPP):
    
    def __init__(self, jid, password):
        super().__init__(jid, password)

        self.add_event_handler("session_start", self.start)

    async def start(self,event):
        self.send_presence()
        await self.get_roster()
        print("roster recived")
        self.disconnect()

if __name__ =='__main__':
    parser = ArgumentParser(description=UserClient.__doc__)

    parser.add_argument("-j", dest="jid")
    parser.add_argument("-p", dest="password")

    args = parser.parse_args()

    if args.jid is None:
        args.jid = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")
    
    xmpp = UserClient(args.jid, args.password)
    xmpp.register_plugin('xep_0030')
    xmpp.register_plugin('xep_0004')

    xmpp.connect(address=('alumchat.xyz',5222))
    xmpp.process()