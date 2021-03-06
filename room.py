from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.db import Key
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from datetime import datetime
import urllib

from models import *
from utils import *
import re


class RoomCollectionHandler(webapp.RequestHandler):

    def get(self):
        rooms = Room.all().order('name')
        roomlist = RoomList.all()
        self.response.out.write(template.render('templates/room_collection.html',
                                                {'rooms': rooms, 
                                                 'roomlist': roomlist}
                                                ))

    def post(self):
        name = self.request.get('name')
        room = Room.all().filter('name =', name).get()
        if room:
            self.response.out.write(template.render('templates/room_collection.html',
                                                    {'error_msg': 'A room by that name already exists.',
                                                     'name': name}
                                                    ))
        else:
            room_slug = slugify(name)
            base_slug = room_slug
            i = 1
            while True:  # do-while loop
                room = Room.get_by_key_name(room_slug)
                if not room:
                    break 
                room_slug = base_slug + str(i)
                i += 1
            room = Room(key_name=room_slug, name=name)
            room.put()
            self.redirect('/room/%s' % room_slug)
            

class RoomHandler(webapp.RequestHandler):

    def get(self, room_slug):
        room = Room.get_by_key_name(room_slug)
        if not room:
            # room doesn't exist
            self.error(404)
            self.response.out.write("no such room")
            return
            
        upload_url = blobstore.create_upload_url('/room/%s/upload' % room_slug)
        
        # return (up to) last 70 messages
        # FIXME should define '70' as a constant
        # need to enumerate query results to access last message below
        # add a second .filter below to hide topic/join/part from template on render
        # filter('event =', 'message') this appears to break the user list though :(
        messages = [m for m in reversed(Message.all().filter('room =', room).order('-timestamp').fetch(70))]
        account = get_account()
        roomlist_query = RoomList.all()
        roomlist_query.filter('room = ', room)
        roomlist = roomlist_query.filter('account = ', account).get()
        if not roomlist:
            #add us to the room we've just joined.
            roomlist = RoomList(account=account, room=room)
            roomlist.put()
            #send a message to update everyone elses contact list
            user = users.get_current_user()
            sender = Account.all().filter('user =', user).get()
            timestamp = datetime.now()
            extra = sender.gravatar_tag
            message = Message(sender=sender, room=room, timestamp=timestamp,
                              event=Message_event_codes['join'], extra=extra)
            message.put()
            
        roomlist = RoomList.all().filter('room = ', room)
        messages = [transform_message(m) for m in messages]
        context = {
            'room': room,
            'account': account,
            'roomlist': roomlist,
            'messages': messages,
            'message_event_names': Message_event_names,
            'upload_url': str(upload_url)
            }
        if messages:
            context['message_last_key'] = messages[-1].key()
        self.response.out.write(template.render('templates/room.html', context))

                                                    
class LeaveHandler(webapp.RequestHandler):
    
    def post(self, room_slug):
        room = Room.get_by_key_name(room_slug)
        account = get_account()
        leave_room(room=room, account=account)
        self.redirect('/room/')

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    def post(self, room_slug):
        upload_files = self.get_uploads('file')
        blob_info = upload_files[0]
        timestamp = datetime.now()
        account = get_account()
        room = Room.get_by_key_name(room_slug)
        blob_key = str(blob_info.key())
        content = '%s/room/%s/download/%s' % (self.request.application_url, room_slug, blob_key)
        message = Message(sender=account, room=room, timestamp=timestamp,
                          event=Message_event_codes['upload'], content=content, extra=blob_key)
        message.put()
        self.redirect('/room/%s/upload/%s/success' % (room_slug, blob_info.key()))

class UploadSuccessHandler(webapp.RequestHandler):
    def get(self, room_slug, file_id):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.out.write('%s/room/%s/download/%s' % (self.request.host_url, room_slug, file_id))


class DownloadHandler(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, room_slug, resource):
        resource = str(urllib.unquote(resource))
        blob_info = blobstore.BlobInfo.get(resource)
        self.send_blob(blob_info, save_as=blob_info.filename)



application = webapp.WSGIApplication([('/room/', RoomCollectionHandler),
                                      (r'/room/([^/]+)', RoomHandler),
                                      (r'/room/([^/]+)/leave', LeaveHandler),
                                      (r'/room/([^/]+)/upload', UploadHandler),
                                      (r'/room/([^/]+)/upload/([^/]+)/success', UploadSuccessHandler),
                                      (r'/room/([^/]+)/download/([^/]+)', DownloadHandler)],
                                     debug=True)

def main():
    webapp.template.register_template_library('filters')
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
