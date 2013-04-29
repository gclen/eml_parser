#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Georges Toth (c) 2013 <georges@trypill.org>
#
# eml_parser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# eml_parser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with eml_parser.  If not, see <http://www.gnu.org/licenses/>.
#
#
# Functionality inspired by:
#   https://github.com/CybOXProject/Tools/blob/master/scripts/email_to_cybox/email_to_cybox.py
#   https://github.com/iscoming/eml_parser/blob/master/eml_parser.py
#

import sys
import email
import getopt
import re
import uuid
import datetime
import base64
import hashlib
import quopri



def get_raw_body_text(msg):
  raw_body = []

  if not msg.is_multipart():
    # Treat text document attachments as belonging to the body of the mail.
    # Attachments with a file-extension of .htm/.html are implicitely treated
    # as text as well in order not to escape later checks (e.g. URL scan).
    if (not msg.has_key('content-disposition') and msg.get_content_maintype() == 'text') or\
      (msg.get_filename('').lower().endswith('.html') or msg.get_filename('').lower().endswith('.htm')):
      encoding = msg.get('content-transfer-encoding', '').lower()

      charset = msg.get_content_charset()
      if not charset:
        raw_body_str = msg.get_payload(decode=True)
      else:
        raw_body_str = msg.get_payload(decode=True).decode(charset, 'ignore')

      raw_body.append((encoding, raw_body_str))
  else:
    for part in msg.get_payload():
      raw_body.extend(get_raw_body_text(part))
  
  return raw_body


def get_file_extension(filename):
  extension = ''
  dot_idx = filename.rfind('.')

  if dot_idx != -1:
    extension = filename[dot_idx+1:]
  
  return extension


def get_file_hashes(data):
  hashalgo = ['md5', 'sha1', 'sha256', 'sha384', 'sha512']
  hashes = {}

  for k in hashalgo:
    ha = getattr(hashlib, k)
    h = ha()
    h.update(data)
    hashes[k] = h.hexdigest()

  return hashes


def decode_field(msg, field, default):
  '''Try to get the specified field using the Header module.
     If there is also an associated encoding, try to decode the
     field and return it, else return a specified default value.'''
  text = default

  try:
    _raw = email.Header.Header(field)
    _decoded = email.Header.decode_header(_raw)
    _text = _decoded[0][0]
    charset = _decoded[0][1]
    if charset:
      text = _test.decode(charset, 'ignore')
  except:
    pass

  return text


def decode_email(eml_file, include_raw_body=False, include_attachment_data=False):
  fp = open(eml_file)
  msg = email.message_from_file(fp)
  fp.close()

  maila = {}  

  # parse and decode subject
  subject = msg.get('subject')
  maila['subject'] = decode_field(msg, 'subject', subject)

  # messageid
  maila['message_id'] = msg.get('Message-ID', '')
  
  # parse and decode from
  # @TODO verify if this hack is necessary for other e-mail fields as well
  m = re.search(r'<\s*([a-z0-9.\-]+@[a-z0-9.\-]+[.][a-z]{2,4})\s*>', msg.get('from', '').lower())
  if m:
    maila['from'] = m.group(1)
  else:
    from_ = email.utils.parseaddr(msg.get('from', '').lower())
    maila['from'] = from_[1]

  # parse and decode to
  to = email.utils.getaddresses(msg.get_all('to', []))
  maila['to'] = []
  for m in to:
    if not m[1] == '':
      maila['to'].append(m[1].lower())

  # parse and decode Cc
  cc = email.utils.getaddresses(msg.get_all('Cc', []))
  maila['cc'] = []
  for m in cc:
    if not m[1] == '':
      maila['cc'].append(m[1].lower())

  # parse and decode Date
  date_ = email.utils.parsedate_tz(msg.get('Date'))

  if date_:
    ts = email.utils.mktime_tz(date_)
    d = datetime.datetime.utcfromtimestamp(ts)
    maila['date'] = d
  else:
    date_ = email.utils.parsedate(msg.get('Date'))
    d = datetime.datetime.fromtimestamp(ts)
    maila['date'] = d

  # sender ip
  maila['x-originating-ip'] = msg.get('x-originating-ip', '').strip('[]')

  # mail receiver path
  # @TODO parse case where domain is specified but in parantheses only an IP
  maila['received'] = []

  for m in msg.get_all('Received'):
    m = re.sub(r'(\r|\n|\s|\t)+', ' ', m.lower())
    f, b = m.split('by')

    b_d = re.search(r'(localhost|[a-z0-9.\-]+[.][a-z]{2,4})', b)
    f_d = re.search(r'from\s+(localhost|[a-z0-9\-]+|[a-z0-9.\-]+[.][a-z]{2,4})\s+(?:\((localhost|[a-z0-9.\-]+[.][a-z]{2,4})?\s*\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]\))?', f)
    f_d = re.search(r'from\s+(localhost|[a-z0-9\-]+|[a-z0-9.\-]+[.][a-z]{2,4})\s+(?:\((localhost|[a-z0-9.\-]+[.][a-z]{2,4})?\s*\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]\))?', f.lower())
    for_d = re.search(r'for\s+<?([a-z0-9.\-]+@[a-z0-9.\-]+[.][a-z]{2,4})>?', m.lower())

    if for_d:
      maila['to'].append(for_d.group(1))

    if f_d:
      if not f_d.group(2):
        f_d_2 = ''
      else:
        f_d_2 = f_d.group(2)
      if not f_d.group(3):
        f_d_3 = ''
      else:
        f_d_3 = f_d.group(3)

      f = '{0} ({1} [{2}])'.format(f_d.group(1), f_d_2, f_d_3)
      b = b_d.group(1)

    maila['received'].append([f, b])

  # get raw header
  raw_body = get_raw_body_text(msg)
  if include_raw_body:
    maila['raw_body'] = raw_body
  else:
    maila['raw_body'] = []

  # parse any URLs found in the body
  url = r'''(?i)\b((?:(hxxps?|https?|ftp)://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?]))'''
  url_re = re.compile(url, re.VERBOSE | re.MULTILINE)
  
  list_observed_urls = []

  for body_tup in raw_body: 
      encoding = body_tup[0]
      body = body_tup[1]
  
      for match in url_re.findall(body):
          found_url = match[0].replace('hxxp', 'http')
          
          if found_url not in list_observed_urls:
              list_observed_urls.append(found_url)

  maila['urls'] = list_observed_urls

  # parse attachments
  attachments = {}

  if msg.is_multipart():
    counter = 1

    for part in msg.get_payload():
      if part.has_key('content-disposition'):
        # if it's an attachment-type, pull out the filename
        # and calculate the size in bytes
        data = part.get_payload(decode=True)
        file_size = len(data)

        filename = part.get_filename('')
        if filename == '':
          filename = 'part-%03d' % (counter)
        else:
          filename = decode_field(part, filename, filename)

        extension = get_file_extension(filename)
        hashes = get_file_hashes(data)

        file_id = str(uuid.uuid1())
        attachments[file_id] = {}
        attachments[file_id]['filename'] = filename
        attachments[file_id]['size'] = file_size
        attachments[file_id]['extension'] = extension
        attachments[file_id]['hashes'] = hashes

        if include_attachment_data:
          attachments[file_id]['raw'] = base64.b64encode(data)

      counter += 1

  maila['attachments'] = attachments

  return maila


def main():
  opts, args = getopt.getopt(sys.argv[1:], 'i:')
  msgfile = None
  
  for o, k in opts:
    if o == '-i':
      msgfile = k

  print decode_email(msgfile)
  #print decode_email(msgfile, include_raw_body=True, include_attachment_data=True)


if __name__ == '__main__':
  main()
